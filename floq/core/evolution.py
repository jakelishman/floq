import numba
import numpy as np
import scipy.sparse.linalg
import collections
import logging
from .. import linalg

_log = logging.getLogger(__name__)

Eigensystem = collections.namedtuple('Eigensystem', (
                                         'frequency',
                                         'quasienergies',
                                         'k_eigenvectors',
                                         'initial_floquet_bras',
                                         'abstract_ket_coefficients',
                                         'k_derivatives',
                                    ))

def eigensystem(hamiltonian, dhamiltonian, n_zones, frequency, decimals=8,
                sparse=True):
    """
    Calculate the time-invariant eigensystem of the Floquet system.  This needs
    to be recalculated whenever the Hamiltonian (or its derivatives) change, but
    not if the time changes.  The result of this can be passed to the other
    calculation routines.

    If the Hamiltonian's derivative is given as `None`, then the derivatives of
    the `K` matrix won't be build, which saves time but prevents the usage of
    the `du_dcontrols()` function.

    Arguments --
    hamiltonian: 3D np.array of complex --
        This must be the matrix of a Hamiltonian, split into Fourier components
        in the same manner used in the return values of
        `floq.System.hamiltonian()`.

    dhamiltonian: 4D np.array of complex | None --
        Optionally, the matrix form of the derivatives of a Hamiltonian, as in
        the output of `floq.System.dhamiltonian()`.  If not supplied, then the
        resulting `Eigensystem` cannot be used with the `du_dcontrols()`
        function.

    n_zones: odd int --
        The number of Brillouin zones to use when creating the Floquet matrix.

    frequency: float --
        The frequency with which the Hamiltonian is periodic.

    decimals: int --
        The number of decimal places of precision to use when comparing floats
        for equality.

    sparse: bool -- Whether to use sparse matrix algebra.

    Returns:
    Eigensystem --
        A collection of parameters that are not time-dependent, which can be
        passed to the time-specific functions.
    """
    n_components, dimension = hamiltonian.shape[0:2]
    k = assemble_k(hamiltonian, n_zones, frequency)
    if sparse:
        k = scipy.sparse.csc_matrix(k)
    quasienergies, k_eigenvectors = diagonalise(k, dimension, frequency,
                                                decimals)
    # Sum the eigenvectors along the Fourier-mode axis at `time = 0` to contract
    # the abstract Hilbert space back to the original one.
    initial_floquet_bras = np.conj(np.sum(k_eigenvectors, axis=1))
    fourier_modes = np.arange((1-n_zones)//2, 1 + (n_zones//2))
    abstract_ket_coefficients = 1j * frequency * fourier_modes
    if dhamiltonian is None:
        k_derivatives = None
    else:
        n_parameters = dhamiltonian.shape[0]
        k_derivatives = assemble_dk(dhamiltonian, n_zones)
    return Eigensystem(frequency, quasienergies, k_eigenvectors,
                       initial_floquet_bras, abstract_ket_coefficients,
                       k_derivatives)

@numba.jit(nopython=True)
def current_floquet_kets(eigensystem, time):
    """
    Get the Floquet basis kets at a given time.  These are the
        |psi_j(t)> = exp(-i energy[j] t) |phi_j(t)>,
    using the notation in Marcel's thesis, equation (1.13).
    """
    weights = np.exp(time * eigensystem.abstract_ket_coefficients)
    weights = weights.reshape((1, -1, 1))
    return np.sum(weights * eigensystem.k_eigenvectors, axis=1)

@numba.jit(nopython=True)
def d_current_floquet_kets(eigensystem, time):
    """
    Get the time derivatives of the Floquet basis kets
        (d/dt)|psi_j(t)> = -i energy[j] exp(-i energy[j] t) |phi_j(t)>
                           + exp(-i energy[j] t) (d/dt)|phi_j(t)>,
    which are used in calculating `dU/dt`.
    """
    weights = np.exp(time * eigensystem.abstract_ket_coefficients)
    weights = weights * eigensystem.abstract_ket_coefficients
    weights = weights.reshape((1, -1, 1))
    return np.sum(weights * eigensystem.k_eigenvectors, axis=1)

@numba.jit(nopython=True)
def u(eigensystem, time):
    """
    Calculate the time-evolution operator at a certain time, using a
    pre-computed eigensystem.
    """
    dimension = eigensystem.quasienergies.shape[0]
    out = np.zeros((dimension, dimension), dtype=np.complex128)
    kets = current_floquet_kets(eigensystem, time)
    energy_phases = np.exp(-1j * time * eigensystem.quasienergies)
    # This sum _can_ be achieved using only vectorised numpy operations, but it
    # involves allocating space for the whole set of outer products.  Easier to
    # just use numba to compile the loop.
    for mode in range(dimension):
        out += np.outer(energy_phases[mode] * kets[mode],
                        eigensystem.initial_floquet_bras[mode])
    return out

@numba.jit(nopython=True)
def du_dt(eigensystem, time):
    """
    Calculate the time derivative of a time-evolution operator at a certain
    time, using a pre-computed eigensystem.
    """
    dimension = eigensystem.quasienergies.shape[0]
    out = np.zeros((dimension, dimension), dtype=np.complex128)
    # Manually allocate calculation space for inside the loop.
    tmp = np.zeros_like(out)
    # These two function calls have some redundancy, but it's not really
    # important in the scheme of things.
    kets = current_floquet_kets(eigensystem, time)
    dkets_dt = d_current_floquet_kets(eigensystem, time)
    energy_factors = -1j * eigensystem.quasienergies
    energy_phases = np.exp(time * energy_factors)
    for mode in range(dimension):
        # Use the pre-allocated computation space to save allocations.
        np.outer(energy_phases[mode] * dkets_dt[mode],
                 eigensystem.initial_floquet_bras[mode], out=tmp)
        out += tmp
        np.outer(energy_phases[mode] * kets[mode],
                 eigensystem.initial_floquet_bras[mode], out=tmp)
        out += energy_factors[mode] * tmp
    return out

@numba.jit(nopython=True)
def conjugate_rotate_into(out, input, amount):
    """
    Equivalent to `out = np.conj(np.roll(input, amount, axis=0))`, but `roll()`
    isn't supported by numba.  Also, we can directly write into `out` so we
    don't have any allocations in tight loops.
    """
    if amount < 0:
        out[:amount] = np.conj(input[abs(amount):])
        out[amount:] = np.conj(input[:abs(amount)])
    elif amount > 0:
        out[amount:] = np.conj(input[:-amount])
        out[:amount] = np.conj(input[-amount:])
    else:
        out[:] = np.conj(input)

@numba.jit(nopython=True)
def integral_factors(eigensystem, time):
    """
    Calculate the "integral factors" for use in the control-derivatives of the
    time-evolution operator.  These are the
        e(j, j'; delta mu)
    from equation (1.48) in Marcel's thesis.
    """
    # This function is comparatively long compared to the old version because it
    # does some questionable loop reorganisation to prevent `if` statements in
    # deeply nested loops.
    n_zones = eigensystem.k_eigenvectors.shape[1]
    dimension = eigensystem.k_eigenvectors.shape[2]
    energies = eigensystem.quasienergies
    frequency = eigensystem.frequency
    energy_phases = np.exp(-1j * time * energies)
    differences = np.arange(1.0 - n_zones, n_zones)
    diff_exponentials = np.exp(1j * time * frequency * differences)
    out = np.empty((differences.shape[0], dimension, dimension),
                   dtype=np.complex128)
    # Fill diagonal of 0 difference, then treat it specially to avoid an `if`
    # statement in a tightly nested loop.  Can be replaced by
    #   np.fill_diagonal(out[n_zones - 1], -1j * time * energy_phases)
    # once numba 0.40 is out.
    diag = -1j * time * energy_phases
    for i in range(energies.shape[0]):
        out[n_zones - 1, i, i] = diag[i]
    for i in range(energies.shape[0]):
        for j in range(i):
            value = (energy_phases[i] - energy_phases[j])\
                    / (energies[i] - energies[j])
            out[n_zones - 1, i, j] = out[n_zones - 1, j, i] = value
    # Handle all the rest of the values, making sure to avoid the zero
    # difference case.
    # Handle negative differences first.
    for diff_index in range(n_zones - 1):
        separation = frequency * differences[diff_index]
        exponential = diff_exponentials[diff_index]
        for i in range(energies.shape[0]):
            numer = energy_phases[i] - energy_phases*exponential
            denom = energies[i] + separation - energies
            out[diff_index, i] = numer / denom
    for diff_index in range(n_zones, differences.shape[0]):
        separation = frequency * differences[diff_index]
        exponential = diff_exponentials[diff_index]
        for i in range(energies.shape[0]):
            numer = energy_phases[i] - energy_phases*exponential
            denom = energies[i] + separation - energies
            out[diff_index, i] = numer / denom
    return out

@numba.jit(nopython=True)
def combined_factors(eigensystem, time):
    """
    Calculate the "combined factors" for use in the control-derivatives of the
    time evolution operator.  These are the
        f(j, j'; delta mu)
    from equations (1.50) and (2.7) in Marcel's thesis.
    """
    n_parameters = eigensystem.k_derivatives.shape[0]
    n_zones = eigensystem.k_eigenvectors.shape[1]
    dimension = eigensystem.k_eigenvectors.shape[2]
    factors = np.empty((2*n_zones - 1, dimension, dimension, n_parameters),
                       dtype=np.complex128)
    rolled_k_eigenbra = np.zeros((n_zones, dimension),
                                 dtype=np.complex128)
    k_eigenkets = eigensystem.k_eigenvectors
    energies = eigensystem.quasienergies
    integral_terms = integral_factors(eigensystem, time)
    for diff_index, diff in enumerate(range(1 - n_zones, n_zones)):
        for i in range(dimension):
            conjugate_rotate_into(rolled_k_eigenbra, k_eigenkets[i], diff)
            for j in range(dimension):
                for parameter in range(n_parameters):
                    expectation = rolled_k_eigenbra.ravel()\
                                  @ eigensystem.k_derivatives[parameter]\
                                  @ k_eigenkets[j].ravel()
                    factors[diff_index, i, j, parameter] =\
                        integral_terms[diff_index, i, j] * expectation
    return factors

@numba.jit(nopython=True)
def du_dcontrols(eigensystem, time):
    """
    Calculate the derivatives of time-evolution operator with respect to the
    control parameters of the Hamiltonian at a certain time, using a
    pre-computed eigensystem.  This is only possible if the eigensystem was
    created using the Hamiltonian derivatives as well.
    """
    n_parameters = eigensystem.k_derivatives.shape[0]
    n_zones, dimension = eigensystem.k_eigenvectors.shape[1:3]
    out = np.zeros((n_parameters, dimension, dimension), dtype=np.complex128)
    if n_parameters == 0:
        return out
    factors = combined_factors(eigensystem, time)
    current_kets = current_floquet_kets(eigensystem, time)
    k_eigenbras = np.conj(eigensystem.k_eigenvectors)
    # Keep an extra dimension so we can broadcast the multiplication of the
    # per-control-parameter factors with the outer product.  This probably just
    # gets optimised into another loop internally, but makes the code here a
    # little tidier (one fewer level of indentation!).
    projector = np.empty((1, dimension, dimension), dtype=np.complex128)
    for i in range(dimension):
        for j in range(dimension):
            for zone_i in range(n_zones - 1, -1, -1):
                np.outer(current_kets[i], k_eigenbras[j, zone_i], out=projector)
                for diff_i in range(zone_i, zone_i + n_zones):
                    factor = factors[diff_i, i, j].reshape(n_parameters, 1, 1)
                    out += factor * projector
    return out

@numba.jit(nopython=True)
def assemble_k(hf, nz, omega):
    nc, dim = hf.shape[0:2]
    k_dim = dim * nz
    hf_max = (nc - 1) // 2
    k = np.zeros((k_dim, k_dim), dtype=np.complex128)
    for n in range(-hf_max, hf_max + 1):
        current = hf[linalg.n_to_i(n, nc)]
        row = max(0, n)  # if n < 0, start at row 0
        col = max(0, -n)  # if n > 0, start at col 0
        stop_row = min(nz - 1 + n, nz - 1)
        stop_col = min(nz - 1 - n, nz - 1)
        while row <= stop_row and col <= stop_col:
            if n == 0:
                block = current + np.eye(dim) * omega * linalg.i_to_n(row, nz)
                linalg.set_block(block, k, dim, nz, row, col)
            else:
                linalg.set_block(current, k, dim, nz, row, col)
            row = row + 1
            col = col + 1
    return k

@numba.jit(nopython=True)
def assemble_dk(dhf, nz):
    npm, nc, dim = dhf.shape[0:3]
    k_dim = nz * dim
    dk = np.empty((npm, k_dim, k_dim), dtype=np.complex128)
    for c in range(npm):
        dk[c, :, :] = assemble_k(dhf[c], nz, 0.0)
    return dk

def first_brillouin_zone(eigenvalues, eigenvectors, n_values, edge):
    """
    Return the `n_values` eigenvalues (and corresponding eigenvectors) which
    fall within the first "Brillioun zone" whos edge is `edge`.  This function
    takes care to select values from only one edge of the zone, and raises a
    `RuntimeError` if it cannot safely do so.

    The inputs `eigenvalues` and `edge` must be rounded to the desired
    precision for this function.

    Arguments:
    eigenvalues: 1D np.array of float --
        The eigenvalues to choose from.  This should be rounded to the desired
        precision (because the floating-point values will be compared directly
        to the edge value).

    eigenvectors: 2D np.array of complex --
        The eigenvectors corresponding to the eigenvalues.  The first index runs
        over the number of vectors, so `eigenvalues[i]` is the eigenvalue
        corresponding to the eigenvector `eigenvectors[i]`.  Note: this is the
        transpose of the return value of `np.linalg.eig` and family.

    n_values: int -- The number of eigenvalues to find.

    edge: float --
        The edge of the first Brillioun zone.  This should be rounded to the
        desired precision.

    Returns:
    eigenvalues: 1D np.array of float -- The selected eigenvalues (sorted).
    eigenvectors: 2D np.array of complex --
        The eigenvectors corresponding to the selected eigenvalues.  The first
        index corresponds to the index of the `eigenvalues` output.
    """
    order = eigenvalues.argsort()
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[order]
    lower = np.searchsorted(eigenvalues, -edge, side='left')
    upper = np.searchsorted(eigenvalues, edge, side='right')
    n_lower_edge = n_upper_edge = 0
    while eigenvalues[lower + n_lower_edge] == -edge:
        n_lower_edge += 1
    # Additional `-1` because `searchsorted(side='right')` gives us the index
    # after the found element.
    while eigenvalues[upper - n_upper_edge - 1] == edge:
        n_upper_edge += 1
    n_not_on_edge = (upper - n_upper_edge) - (lower + n_lower_edge)
    log_message = " ".join([
        f"Needed {n_values} eigenvalues in the first zone.",
        f"Found {n_lower_edge}, {n_not_on_edge}, {n_upper_edge} on the",
        "lower edge, centre zone, upper edge respectively.",
    ])
    _log.debug(log_message)
    if n_not_on_edge == n_values:
        lower, upper = lower + n_lower_edge, upper - n_upper_edge
    elif n_not_on_edge + n_lower_edge == n_values:
        lower, upper = lower, upper - n_upper_edge
    elif n_not_on_edge + n_upper_edge == n_values:
        lower, upper = lower + n_lower_edge, upper
    else:
        exception_message = " ".join([
            "Could not resolve the first Brillouin zone safely.",
            "You could try increasing the tolerance (decreasing the 'decimals'",
            "field), or adding a small constant term to your Hamiltonian.",
        ])
        raise RuntimeError(exception_message)
    return eigenvalues[lower:upper], eigenvectors[lower:upper]

def diagonalise(k, h_dimension, frequency, decimals):
    """
    Find the eigenvalues and eigenvectors of the Floquet matrix `k`
    corresponding to the first "Brillioun zone".  The eigenvectors corresponding
    to degenerate eigenvalues are orthogonalised, where degeneracy and
    orthoganlisation are done to a precision defined by `decimals`.

    Arguments --
    k: 2D np.array of complex | scipy.sparse.spmatrix --
        The full matrix form of the Floquet matrix.  This can be given as either
        a dense `numpy` array, or any form of `scipy.sparse` array.  In the
        latter case, the eigenvalues and vectors are found iteratively with a
        shift-invert method, which can cause issues when eigenvalues fall
        exactly on zero, or exactly on the border.  The former case can
        typically be solved by adding a term proportional to the identity onto
        the Hamiltonian, and the latter should largely be taken care of by the
        code.

    h_dimension: int -- The dimension of the Hamiltonian.

    frequency: float --
        The angular frequency with which the Hamiltonian is periodic.

    decimals: int --
        The number of decimal places to use as a precision for orthogonalisation
        and comparison of degenerate eigenvalues.

    Returns --
    eigenvalues: 1D np.array of float --
        The eigenvalues of the `k` matrix which fall within the first Brillouin
        zone.
    eigenvectors: np.array(dtype=np.complex128,
                           shape=(h_dimension, n_zones, h_dimension)) --
        The eigenvectors corresponding to the chosen eigenvalues.  The first
        index matches the index of `eigenvalues`, then each eigenvector is
        shaped into the Brillouin zone blocks, so the second index runs along
        Floquet kets corresponding to a certain (potentially degenerate)
        quasi-energy.
    """
    if isinstance(k, scipy.sparse.spmatrix):
        # We get twice as many eigenvalues as necessary so we can guarantee we
        # have a full set in the first Brillouin zone, even if all of them fall
        # on the very edge of the zone.  If this were to happen and we were only
        # taking the absolutely necessary number of eigenvalues, we would
        # sometimes duplicate an eigenvector without intending to.
        eigenvalues, eigenvectors =\
            scipy.sparse.linalg.eigs(k, k=2*h_dimension, sigma=0.0)
    else:
        eigenvalues, eigenvectors = np.linalg.eig(k)
    eigenvalues = np.round(np.real(eigenvalues), decimals=decimals)
    eigenvectors = np.transpose(eigenvectors)
    edge = np.round(0.5 * frequency, decimals=decimals)
    eigenvalues, eigenvectors = first_brillouin_zone(eigenvalues, eigenvectors,
                                                     h_dimension, edge)
    for degeneracy in find_duplicates(eigenvalues):
        eigenvectors[degeneracy] = linalg.gram_schmidt(eigenvectors[degeneracy])
    n_zones = k.shape[0] // h_dimension
    return eigenvalues, eigenvectors.reshape(h_dimension, n_zones, h_dimension)

def find_duplicates(array):
    """
    Given a sorted 1D array of values, return an iterator where each element
    corresponds to one degenerate eigenvalue, and the element is a list of
    indices where that eigenvalue occurs.
    For example,
        find_duplicates([0, 0, 0, 1, 2, 2, 3])
    returns
        [[0, 1, 2], [4, 5]].
    Arguments --
    array: 1D sorted np.array --
        The array to find duplicates in.  Should be rounded to the required
        precision already.
    Returns --
    duplicate_sets: iterator of np.array of int --
        An iterator yielding arrays of the indices of each duplicate entry.
        Entries which are not duplicated will not be referenced in the output.
    """
    indices = np.arange(array.shape[0])
    _, start_indices = np.unique(array, return_index=True)
    # start_indices will always contain 0 first, but np.split doesn't need it.
    return filter(lambda x: x.size > 1, np.split(indices, start_indices[1:]))
