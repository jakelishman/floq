import numpy as np
import floq

# Rydberg atoms as test problem;
# full commented implementation at github.com/sirmarcel/ryd

# Factors encoding units and physical constants
factor_hdip = 9.75009e+2
factor_haf = 1.27954e+1

def rydberg_atoms(n_components, rvec, mu, delta, omega, **kwargs):
    h_base = np.zeros((2*n_components + 1, 16, 16), dtype=np.complex128)
    h_static = generate_ha(delta) + generate_hdip(np.linalg.norm(rvec),
                                                rvec[0], rvec[1], rvec[2],
                                                mu, factor_hdip)
    h_base[n_components] = h_static
    dh_base = generate_dhf(n_components, mu, factor_haf)
    def _hamiltonian(controls):
        update_hf(h_base, n_components, controls, mu, factor_haf)
        return h_base
    if 'nz' not in kwargs:
        kwargs['nz'] = 11
    if 'max_nz' not in kwargs:
        kwargs['max_nz'] = 1001
    return floq.System(_hamiltonian, lambda controls: dh_base,
                       omega=2*np.pi*omega, **kwargs)

def update_hf(hf, ncomp, controls, mu, factor):
    """In the supplied array hf, update the control entries, in memory.

    This corresponds to an efficient expression of the Atom-Field Hamiltonian
    called H_AF in the text.

    Directly updates the given array, not instantiating a new one, to avoid
    allocating memory needlessly. If the control pulse is structured as described
    in the RydbergAtoms class, its Fourier components are arranged as

        (a(-ncomp) a(-ncomp+1) ... a(1) 0 a(1) a(2) ... a(ncomp))

    and so we only need to go through half the array due to the symmetry.
    """
    for k in range(ncomp):
        a = controls[-2*k-2]  # linearly polarized field component
        b = controls[-2*k-1]  # circularly polarized field component

        rabi_a = -1j*mu*a*0.25*factor
        rabi_b = 1j*mu*b*0.25*factor

        # Selectively update the necessary entries
        # This is ugly, but I couldn't find an efficient other way
        hf[k, 0, 2] = rabi_a
        hf[-k-1, 0, 2] = -rabi_a
        hf[k, 0, 8] = rabi_a
        hf[-k-1, 0, 8] = -rabi_a
        hf[k, 1, 9] = rabi_a
        hf[-k-1, 1, 9] = -rabi_a
        hf[k, 2, 0] = rabi_a
        hf[-k-1, 2, 0] = -rabi_a
        hf[k, 2, 10] = rabi_a
        hf[-k-1, 2, 10] = -rabi_a
        hf[k, 3, 11] = rabi_a
        hf[-k-1, 3, 11] = -rabi_a
        hf[k, 4, 6] = rabi_a
        hf[-k-1, 4, 6] = -rabi_a
        hf[k, 6, 4] = rabi_a
        hf[-k-1, 6, 4] = -rabi_a
        hf[k, 8, 0] = rabi_a
        hf[-k-1, 8, 0] = -rabi_a
        hf[k, 8, 10] = rabi_a
        hf[-k-1, 8, 10] = -rabi_a
        hf[k, 9, 1] = rabi_a
        hf[-k-1, 9, 1] = -rabi_a
        hf[k, 10, 2] = rabi_a
        hf[-k-1, 10, 2] = -rabi_a
        hf[k, 10, 8] = rabi_a
        hf[-k-1, 10, 8] = -rabi_a
        hf[k, 11, 3] = rabi_a
        hf[-k-1, 11, 3] = -rabi_a
        hf[k, 12, 14] = rabi_a
        hf[-k-1, 12, 14] = -rabi_a
        hf[k, 14, 12] = rabi_a
        hf[-k-1, 14, 12] = -rabi_a
        hf[k, 0, 3] = rabi_b
        hf[-k-1, 0, 3] = -rabi_b
        hf[k, 0, 12] = rabi_b
        hf[-k-1, 0, 12] = -rabi_b
        hf[k, 1, 13] = rabi_b
        hf[-k-1, 1, 13] = -rabi_b
        hf[k, 2, 14] = rabi_b
        hf[-k-1, 2, 14] = -rabi_b
        hf[k, 3, 0] = rabi_b
        hf[-k-1, 3, 0] = -rabi_b
        hf[k, 3, 15] = rabi_b
        hf[-k-1, 3, 15] = -rabi_b
        hf[k, 4, 7] = rabi_b
        hf[-k-1, 4, 7] = -rabi_b
        hf[k, 7, 4] = rabi_b
        hf[-k-1, 7, 4] = -rabi_b
        hf[k, 8, 11] = rabi_b
        hf[-k-1, 8, 11] = -rabi_b
        hf[k, 11, 8] = rabi_b
        hf[-k-1, 11, 8] = -rabi_b
        hf[k, 12, 0] = rabi_b
        hf[-k-1, 12, 0] = -rabi_b
        hf[k, 12, 15] = rabi_b
        hf[-k-1, 12, 15] = -rabi_b
        hf[k, 13, 1] = rabi_b
        hf[-k-1, 13, 1] = -rabi_b
        hf[k, 14, 2] = rabi_b
        hf[-k-1, 14, 2] = -rabi_b
        hf[k, 15, 3] = rabi_b
        hf[-k-1, 15, 3] = -rabi_b
        hf[k, 15, 12] = rabi_b
        hf[-k-1, 15, 12] = -rabi_b
    return None


def generate_ha(delta):
    """Generate the single-atom parts of the Hamiltonian."""
    return np.array([[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, -delta, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, -delta, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, -delta, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, -delta, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, -2*delta, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, -2*delta, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, -2*delta, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, -delta, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, -2*delta, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -2*delta, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -2*delta, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -delta, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -2*delta, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -2*delta, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -2*delta]])

def generate_hdip(r, x, y, z, mu, factorhdip):
    """Generate the dipole-dipole part of the Hamiltonian.

    Arguments:
        r, x, y, z: The relative position of the atoms (distance and components).
        mu: matrix element value (see class for definition)
        factor: adjustment factor taking into account various units.
    """
    return np.array([[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, (factorhdip*mu**2*(2*r**2 - 3*(x**2 + y**2)))/(2*r**5), 0, 0, 0, (-3*factorhdip*mu**2*(x +1j*y)*z)/(np.sqrt(2)*r**5), 0, 0, 0, (3*factorhdip*mu**2*(x +1j*y)**2)/(2*r**5), 0, 0, 0], [0, 0, 0, 0, (-3*factorhdip*mu**2*(x -1j*y)*z)/(np.sqrt(2)*r**5), 0, 0, 0, (factorhdip*mu**2*(r**2 - 3*z**2))/r**5, 0, 0, 0, (3*factorhdip*mu**2*(x +1j*y)*z)/(np.sqrt(2)*r**5), 0, 0, 0], [0, 0, 0, 0, (3*factorhdip*mu**2*(x -1j*y)**2)/(2*r**5), 0, 0, 0, (3*factorhdip*mu**2*(x -1j*y)*z)/(np.sqrt(2)*r**5), 0, 0, 0, (factorhdip*mu**2*(2*r**2 - 3*(x**2 + y**2)))/(2*r**5), 0, 0, 0], [0, (factorhdip*mu**2*(2*r**2 - 3*(x**2 + y**2)))/(2*r**5), (-3*factorhdip*mu**2*(x +1j*y)*z)/(np.sqrt(2)*r**5), (3*factorhdip*mu**2*(x +1j*y)**2)/(2*r**5), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, (-3*factorhdip*mu**2*(x -1j*y)*z)/(np.sqrt(2)*r**5), (factorhdip*mu**2*(r**2 - 3*z**2))/r**5, (3*factorhdip*mu**2*(x +1j*y)*z)/(np.sqrt(2)*r**5), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, (3*factorhdip*mu**2*(x -1j*y)**2)/(2*r**5), (3*factorhdip*mu**2*(x -1j*y)*z)/(np.sqrt(2)*r**5), (factorhdip*mu**2*(2*r**2 - 3*(x**2 + y**2)))/(2*r**5), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]])

def generate_dhf(ncomp, mu, factor):
    """Generate the (static) gradient of the Fourier Hamiltonian."""
    npm = 2*ncomp
    nc = 2*ncomp + 1
    dhf = np.zeros([npm, nc, 16, 16], dtype=np.complex128)
    for index in range(0, npm):
        dhf[index] = generate_single_dhf(mu, ncomp, index, factor)
    return dhf

def generate_single_dhf(mu, ncomp, index, factor):
    """Generate a single component of dhf, wrt to control index.

    Since the Hamiltonian is linear in the controls, its gradient is
    static and easy to compute by setting the respective control to 1
    and all others to 0.
    """
    dhf = np.zeros([ncomp*2+1, 16, 16], dtype='complex128')
    controls = np.zeros(2*ncomp)
    controls[index] = 1.0
    update_hf(dhf, ncomp, controls, mu, factor)
    return dhf
