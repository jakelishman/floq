from unittest import TestCase
from tests.assertions import CustomAssertions
import scipy.sparse
import numpy as np
import tests.rabi as rabi
import floq

class TestSetBlock(TestCase):
    def setUp(self):
        self.dim_block = 5
        self.n_block = 3

        self.a, self.b, self.c, self.d, self.e, self.f, self.g, self.h, self.i \
            = [j*np.ones([self.dim_block, self.dim_block]) for j in range(9)]

        matrix = np.bmat([[self.a, self.b, self.c],
                         [self.d, self.e, self.f],
                         [self.g, self.h, self.i]])
        self.original = np.array(matrix)

        total_size = self.dim_block*self.n_block
        self.copy = np.zeros([total_size,total_size])

    def test_set(self):
        # Try to recreate self.original with the new function
        floq.evolution._add_block(self.a, self.copy, self.dim_block, self.n_block, 0, 0)
        floq.evolution._add_block(self.b, self.copy, self.dim_block, self.n_block, 0, 1)
        floq.evolution._add_block(self.c, self.copy, self.dim_block, self.n_block, 0, 2)
        floq.evolution._add_block(self.d, self.copy, self.dim_block, self.n_block, 1, 0)
        floq.evolution._add_block(self.e, self.copy, self.dim_block, self.n_block, 1, 1)
        floq.evolution._add_block(self.f, self.copy, self.dim_block, self.n_block, 1, 2)
        floq.evolution._add_block(self.g, self.copy, self.dim_block, self.n_block, 2, 0)
        floq.evolution._add_block(self.h, self.copy, self.dim_block, self.n_block, 2, 1)
        floq.evolution._add_block(self.i, self.copy, self.dim_block, self.n_block, 2, 2)
        self.assertTrue(np.array_equal(self.copy,self.original))


class TestAssembleK(CustomAssertions):
    def setUp(self):
        self.n_zones = 5
        self.frequency = 1
        dim=2
        a = -1.*np.ones([dim, dim])
        b = np.zeros([dim, dim])
        c = np.ones([dim, dim])
        z = np.zeros([dim, dim])
        i = np.identity(dim)

        self.goalk = np.array(
            np.bmat(
                [[b-2*i, a, z, z, z],
                 [c, b-i, a, z, z],
                 [z, c, b, a, z],
                 [z, z, c, b+i, a],
                 [z, z, z, c, b+2*i]]))
        self.hf = floq.system._canonicalise_operator(np.array([a, b, c]))

    def test_dense(self):
        builtk = floq.evolution.assemble_k(self.hf, self.n_zones, self.frequency)
        self.assertArrayEqual(builtk, self.goalk)

    def test_sparse(self):
        builtk = floq.evolution.assemble_k_sparse(self.hf, self.n_zones,
                                                  self.frequency)
        self.assertTrue(scipy.sparse.issparse(builtk))
        self.assertArrayEqual(builtk.toarray(), self.goalk)

class TestDenseToSparse(CustomAssertions):
    def test_conversion(self):
        goal = floq.types.ColumnSparseMatrix(np.array([1, 2]),
                                             np.array([1, 0, 1]),
                                             np.array([2, 1, 3]))
        built = floq.evolution._dense_to_sparse(np.arange(4).reshape(2, 2))
        self.assertColumnSparseMatrixEqual(built, goal)

class TestAssembledK(CustomAssertions):
    def setUp(self):
        self.n_zones = 5
        dim=2

        a = -1.*np.ones([dim, dim])
        b = np.zeros([dim, dim])
        c = np.ones([dim, dim])
        z = np.zeros([dim, dim])
        i = np.identity(dim)

        dk1 = np.array(
            np.bmat(
                [[b, a, z, z, z],
                 [c, b, a, z, z],
                 [z, c, b, a, z],
                 [z, z, c, b, a],
                 [z, z, z, c, b]]))
        dk2 = np.array(
            np.bmat(
                [[b, b, z, z, z],
                 [a, b, b, z, z],
                 [z, a, b, b, z],
                 [z, z, a, b, b],
                 [z, z, z, a, b]]))

        self.goaldk = [floq.evolution._dense_to_sparse(x) for x in [dk1, dk2]]
        self.dhf = [floq.system._canonicalise_operator(np.array([a, b, c])),
                    floq.system._canonicalise_operator(np.array([b, b, a]))]

    def test_build(self):
        builtdk = floq.evolution.assemble_dk(self.dhf, self.n_zones)
        for i, bdk in enumerate(builtdk):
            self.assertColumnSparseMatrixEqual(bdk, self.goaldk[i])

class TestFindEigensystem(CustomAssertions):
    def setUp(self):
        self.target_vals = np.array([-0.235, 0.753])
        # random matrix with known eigenvalues:
        # {-1.735, -0.747, -0.235, 0.753, 1.265, 2.253}
        k = np.array([[-0.0846814, -0.0015136 - 0.33735j, -0.210771 + 0.372223j,
                       0.488512 - 0.769537j, -0.406266 + 0.315634j, -0.334452 +
                        0.251584j], [-0.0015136 + 0.33735j,
                       0.809781, -0.416533 - 0.432041j, -0.571074 -
                        0.669052j, -0.665971 + 0.387569j, -0.297409 -
                        0.0028969j], [-0.210771 - 0.372223j, -0.416533 +
                        0.432041j, -0.0085791, 0.110085 + 0.255156j,
                       0.958938 - 0.17233j, -0.91924 + 0.126004j], [0.488512 +
                        0.769537j, -0.571074 + 0.669052j,
                       0.110085 - 0.255156j, -0.371663,
                       0.279778 + 0.477653j, -0.496302 + 1.04898j], [-0.406266 -
                        0.315634j, -0.665971 - 0.387569j, 0.958938 + 0.17233j,
                       0.279778 - 0.477653j, -0.731623,
                       0.525248 + 0.0443422j], [-0.334452 - 0.251584j, -0.297409 +
                        0.0028969j, -0.91924 - 0.126004j, -0.496302 - 1.04898j,
                       0.525248 - 0.0443422j, 1.94077]], dtype='complex128')

        e1 = np.array([[0.0321771 - 0.52299j, 0.336377 + 0.258732j],
                       [0.371002 + 0.0071587j, 0.237385 + 0.205185j],
                       [0.525321 + 0.j, 0.0964822 + 0.154715j]])
        e2 = np.array([[0.593829 + 0.j, -0.105998 - 0.394563j],
                       [-0.0737891 - 0.419478j, 0.323414 + 0.350387j],
                       [-0.05506 - 0.169033j, -0.0165495 + 0.199498j]])
        self.target_vecs = np.array([e1, e2])

        omega = 2.1
        dim = 2
        self.vals, self.vecs = floq.evolution.diagonalise(k, dim, omega, 3)

    def test_finds_vals(self):
        self.assertArrayEqual(self.vals, self.target_vals)

    def test_finds_vecs(self):
        self.assertArrayEqual(self.vecs, self.target_vecs, decimals=3)

    def test_casts_as_complex128(self):
        self.assertEqual(self.vecs.dtype, 'complex128')

class TestFindDuplicates(CustomAssertions):
    def test_duplicates(self):
        a = np.round(np.array([1, 2.001, 2.003, 1.999, 3]), decimals=2)
        res = tuple(floq.evolution._find_duplicates(a))
        self.assertEqual(len(res), 1)
        self.assertArrayEqual([1, 2, 3], res[0])

    def test_empty_if_no_dup(self):
        a = np.round(np.array([1, 2.001, 4.003, 8.999, 10]), decimals=2)
        res = tuple(floq.evolution._find_duplicates(a))
        self.assertEqual(res, ())

    def test_multiple_duplicates(self):
        a = np.array([1., 1., 2., 2., 3., 4., 4.])
        res = tuple(floq.evolution._find_duplicates(a))
        self.assertEqual(len(res), 3)
        self.assertArrayEqual([[0, 1], [2, 3], [5, 6]], res)
