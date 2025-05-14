# A .txt file that when renamed conftest.py will allow pytest to flag sparray troubles.
#================== Added to check spmatrix usage ========================
import scipy

def flag_this_call(*args, **kwds):
    raise ValueError("Old spmatrix version of bmat called")

scipy.sparse._construct.bmat = flag_this_call
scipy.sparse._construct.rand = flag_this_call
scipy.sparse._construct.rand = flag_this_call

class _strict_mul_mixin:
    def __mul__(self, other):
        if not scipy.sparse._sputils.isscalarlike(other):
            raise ValueError('Operator * used here! Change to @?')
        return super().__mul__(other)

    def __rmul__(self, other):
        if not scipy.sparse._sputils.isscalarlike(other):
            raise ValueError('Operator * used here! Change to @?')
        return super().__rmul__(other)

    def __imul__(self, other):
        if not scipy.sparse._sputils.isscalarlike(other):
            raise ValueError('Operator * used here! Change to @?')
        return super().__imul__(other)

    def __pow__(self, *args, **kwargs):
        raise ValueError('spmatrix ** found! Use linalg.matrix_power?')

    @property
    def A(self):
        raise TypeError('spmatrix A property found! Use .toarray()')

    @property
    def H(self):
        raise TypeError('spmatrix H property found! Use .conjugate().T')

    def asfptype(self):
        raise TypeError('spmatrix asfptype found! rewrite needed')

    def get_shape(self):
        raise TypeError('spmatrix get_shape found! Use .shape')

    def getformat(self):
        raise TypeError('spmatrix getformat found! Use .shape')

    def getmaxprint(self):
        raise TypeError('spmatrix getmaxprint found! Use .shape')

    def getnnz(self):
        raise TypeError('spmatrix getnnz found! Use .shape')

    def getH(self):
        raise TypeError('spmatrix getH found! Use .shape')

    def getrow(self):
        raise TypeError('spmatrix getrow found! Use .shape')

    def getcol(self):
        raise TypeError('spmatrix getcol found! Use .shape')

    def sum(self, *args, axis=None, **kwds):
        if axis is not None:
            import warnings
            warnings.warn(f'spmatrix sum found using axis={axis}!')
            return super().sum(*args, axis=axis, **kwds)
        else:
            return super().sum(*args, **kwds)


    def mean(self, *args, axis=None, **kwds):
        if axis is not None:
            raise TypeError(f'spmatrix mean found using axis={axis}!')
        return super().mean(*args, **kwds)

    def min(self, *args, axis=None, **kwds):
        if axis is not None:
            import warnings
            warnings.warn(f'spmatrix max found using axis={axis}!')
        return super().min(*args,axis=axis, **kwds)

    def max(self, *args, axis=None, **kwds):
        if axis is not None:
            import warnings
            warnings.warn(f'spmatrix max found using axis={axis}!')
        return super().max(*args, axis=axis, **kwds)

    def argmin(self, *args, axis=None, **kwds):
        if axis is not None:
            raise TypeError(f'spmatrix agrmin found using axis={axis}!')
        return super().argmin(*args, **kwds)

    def argmax(self, *args, axis=None, **kwds):
        if axis is not None:
            raise TypeError(f'spmatrix argmax found using axis={axis}!')
        return super().argmax(*args, **kwds)


class coo_matrix_strict(_strict_mul_mixin, scipy.sparse.coo_matrix):
    pass

class bsr_matrix_strict(_strict_mul_mixin, scipy.sparse.bsr_matrix):
    pass

class csr_matrix_strict(_strict_mul_mixin, scipy.sparse.csr_matrix):
    pass

class csc_matrix_strict(_strict_mul_mixin, scipy.sparse.csc_matrix):
    pass

class dok_matrix_strict(_strict_mul_mixin, scipy.sparse.dok_matrix):
    pass

class lil_matrix_strict(_strict_mul_mixin, scipy.sparse.lil_matrix):
    pass

class dia_matrix_strict(_strict_mul_mixin, scipy.sparse.dia_matrix):
    pass

scipy.sparse.coo_matrix = scipy.sparse._coo.coo_matrix = coo_matrix_strict
scipy.sparse.bsr_matrix = scipy.sparse._bsr.bsr_matrix = bsr_matrix_strict
scipy.sparse.csr_matrix = scipy.sparse._csr.csr_matrix = csr_matrix_strict
scipy.sparse.csc_matrix = scipy.sparse._csc.csc_matrix = csc_matrix_strict
scipy.sparse.dok_matrix = scipy.sparse._dok.dok_matrix = dok_matrix_strict
scipy.sparse.lil_matrix = scipy.sparse._lil.lil_matrix = lil_matrix_strict
scipy.sparse.dia_matrix = scipy.sparse._dia.dia_matrix = dia_matrix_strict

scipy.sparse._compressed.csr_matrix = csr_matrix_strict

scipy.sparse._construct.bsr_matrix = bsr_matrix_strict
scipy.sparse._construct.coo_matrix = coo_matrix_strict
scipy.sparse._construct.csc_matrix = csc_matrix_strict
scipy.sparse._construct.csr_matrix = csr_matrix_strict
scipy.sparse._construct.dia_matrix = dia_matrix_strict

scipy.sparse._extract.coo_matrix = coo_matrix_strict

scipy.sparse._matrix.bsr_matrix = bsr_matrix_strict
scipy.sparse._matrix.coo_matrix = coo_matrix_strict
scipy.sparse._matrix.csc_matrix = csc_matrix_strict
scipy.sparse._matrix.csr_matrix = csr_matrix_strict
scipy.sparse._matrix.dia_matrix = dia_matrix_strict
scipy.sparse._matrix.dok_matrix = dok_matrix_strict
scipy.sparse._matrix.lil_matrix = lil_matrix_strict

del coo_matrix_strict
del bsr_matrix_strict
del csr_matrix_strict
del csc_matrix_strict
del dok_matrix_strict
del lil_matrix_strict
del dia_matrix_strict
#==========================================
