"""
ML Estimation of Spatial Error Model
"""

__author__ = "Luc Anselin luc.anselin@asu.edu,\
              Serge Rey srey@asu.edu, \
              Levi Wolf levi.john.wolf@asu.edu"

import numpy as np
import numpy.linalg as la
from scipy import sparse as sp
from scipy.sparse.linalg import splu as SuperLU
from .utils import RegressionPropsY, RegressionPropsVM, set_warn, get_lags
from . import diagnostics as DIAG
from . import user_output as USER
from . import regimes as REGI
from .w_utils import symmetrize
import pandas as pd
from .output import output, _nonspat_top

try:
    from scipy.optimize import minimize_scalar

    minimize_scalar_available = True
except ImportError:
    minimize_scalar_available = False
from .sputils import spdot, spfill_diagonal, spinv
from libpysal import weights

__all__ = ["ML_Error"]


class BaseML_Error(RegressionPropsY, RegressionPropsVM, REGI.Regimes_Frame):

    """
    ML estimation of the spatial error model (note no consistency
    checks, diagnostics or constants added): :cite:`Anselin1988`

    Parameters
    ----------
    y            : array
                   nx1 array for dependent variable
    x            : array
                   Two dimensional array with n rows and one column for each
                   independent (exogenous) variable, excluding the constant
    w            : Sparse matrix
                   Spatial weights sparse matrix
    method       : string
                   if 'full', brute force calculation (full matrix expressions)
                   if 'ord', Ord eigenvalue calculation
                   if 'LU', LU decomposition for sparse matrices
    epsilon      : float
                   tolerance criterion in mimimize_scalar function and inverse_product
    regimes_att  : dictionary
                   Dictionary containing elements to be used in case of a regimes model,
                   i.e. 'x' before regimes, 'regimes' list and 'cols2regi'


    Attributes
    ----------
    betas        : array
                   kx1 array of estimated coefficients
    lam          : float
                   estimate of spatial autoregressive coefficient
    u            : array
                   nx1 array of residuals
    e_filtered   : array
                   spatially filtered residuals
    predy        : array
                   nx1 array of predicted y values
    n            : integer
                   Number of observations
    k            : integer
                   Number of variables for which coefficients are estimated
                   (including the constant, excluding the rho)
    y            : array
                   nx1 array for dependent variable
    x            : array
                   Two dimensional array with n rows and one column for each
                   independent (exogenous) variable, including the constant
    method       : string
                   log Jacobian method
                   if 'full': brute force (full matrix computations)
                   if 'ord' : Ord eigenvalue method
    epsilon      : float
                   tolerance criterion used in minimize_scalar function and inverse_product
    mean_y       : float
                   Mean of dependent variable
    std_y        : float
                   Standard deviation of dependent variable
    vm           : array
                   Variance covariance matrix (k+1 x k+1) - includes lambda
    vm1          : array
                   2x2 array of variance covariance for lambda, sigma
    sig2         : float
                   Sigma squared used in computations
    logll        : float
                   maximized log-likelihood (including constant terms)

    Examples
    --------
    >>> import numpy as np
    >>> import libpysal
    >>> from libpysal import examples
    >>> from libpysal.examples import load_example
    >>> import spreg
    >>> np.set_printoptions(suppress=True) #prevent scientific format
    >>> south = load_example('South')
    >>> db = libpysal.io.open(south.get_path("south.dbf"),'r')
    >>> y_name = "HR90"
    >>> y = np.array(db.by_col(y_name))
    >>> y.shape = (len(y),1)
    >>> x_names = ["RD90","PS90","UE90","DV90"]
    >>> x = np.array([db.by_col(var) for var in x_names]).T
    >>> x = np.hstack((np.ones((len(y),1)),x))
    >>> w = libpysal.weights.Queen.from_shapefile(south.get_path("south.shp"))
    >>> w.transform = 'r'
    >>> mlerr = spreg.ml.error.BaseML_Error(y,x,w) #doctest: +SKIP
    >>> "{0:.6f}".format(mlerr.lam) #doctest: +SKIP
    '0.299078'
    >>> np.around(mlerr.betas, decimals=4) #doctest: +SKIP
    array([[ 6.1492],
           [ 4.4024],
           [ 1.7784],
           [-0.3781],
           [ 0.4858],
           [ 0.2991]])
    >>> "{0:.6f}".format(mlerr.mean_y) #doctest: +SKIP
    '9.549293'
    >>> "{0:.6f}".format(mlerr.std_y) #doctest: +SKIP
    '7.038851'
    >>> np.diag(mlerr.vm) #doctest: +SKIP
    array([ 1.06476526,  0.05548248,  0.04544514,  0.00614425,  0.01481356,
            0.00143001])
    >>> "{0:.6f}".format(mlerr.sig2[0][0]) #doctest: +SKIP
    '32.406854'
    >>> "{0:.6f}".format(mlerr.logll) #doctest: +SKIP
    '-4471.407067'
    >>> mlerr1 = BaseML_Error(y,x,w,method='ord') #doctest: +SKIP
    >>> "{0:.6f}".format(mlerr1.lam) #doctest: +SKIP
    '0.299078'
    >>> np.around(mlerr1.betas, decimals=4) #doctest: +SKIP
    array([[ 6.1492],
           [ 4.4024],
           [ 1.7784],
           [-0.3781],
           [ 0.4858],
           [ 0.2991]])
    >>> "{0:.6f}".format(mlerr1.mean_y) #doctest: +SKIP
    '9.549293'
    >>> "{0:.6f}".format(mlerr1.std_y) #doctest: +SKIP
    '7.038851'
    >>> np.around(np.diag(mlerr1.vm), decimals=4) #doctest: +SKIP
    array([ 1.0648,  0.0555,  0.0454,  0.0061,  0.0148,  0.0014])
    >>> "{0:.4f}".format(mlerr1.sig2[0][0]) #doctest: +SKIP
    '32.4069'
    >>> "{0:.4f}".format(mlerr1.logll) #doctest: +SKIP
    '-4471.4071'

    """

    def __init__(self, y, x, w, method="full", epsilon=0.0000001, regimes_att=None):
        # set up main regression variables and spatial filters
        self.y = y
        if regimes_att:
            self.x = x.toarray()
        else:
            self.x = x
        self.n, self.k = self.x.shape
        self.method = method
        self.epsilon = epsilon

        # W = w.full()[0] #wait to build pending what is needed
        # Wsp = w.sparse

        ylag = weights.lag_spatial(w, self.y)
        xlag = self.get_x_lag(w, regimes_att)

        # call minimizer using concentrated log-likelihood to get lambda
        methodML = method.upper()
        if methodML in ["FULL", "LU", "ORD"]:
            if methodML == "FULL":
                W = w.full()[0]  # need dense here
                res = minimize_scalar(
                    err_c_loglik,
                    0.0,
                    bounds=(-1.0, 1.0),
                    args=(self.n, self.y, ylag, self.x, xlag, W),
                    method="bounded",
                    tol=epsilon,
                )
            elif methodML == "LU":
                I = sp.identity(w.n)
                Wsp = w.sparse  # need sparse here
                res = minimize_scalar(
                    err_c_loglik_sp,
                    0.0,
                    bounds=(-1.0, 1.0),
                    args=(self.n, self.y, ylag, self.x, xlag, I, Wsp),
                    method="bounded",
                    tol=epsilon,
                )
                W = Wsp
            elif methodML == "ORD":
                # check on symmetry structure
                if w.asymmetry(intrinsic=False) == []:
                    ww = symmetrize(w)
                    WW = np.array(ww.todense())
                    evals = la.eigvalsh(WW)
                    W = WW
                else:
                    W = w.full()[0]  # need dense here
                    evals = la.eigvals(W)
                res = minimize_scalar(
                    err_c_loglik_ord,
                    0.0,
                    bounds=(-1.0, 1.0),
                    args=(self.n, self.y, ylag, self.x, xlag, evals),
                    method="bounded",
                    tol=epsilon,
                )
        else:
            raise Exception("{0} is an unsupported method".format(method))

        self.lam = res.x

        # compute full log-likelihood, including constants
        ln2pi = np.log(2.0 * np.pi)
        llik = -res.fun - self.n / 2.0 * ln2pi - self.n / 2.0

        self.logll = llik

        # b, residuals and predicted values

        ys = self.y - self.lam * ylag
        xs = self.x - self.lam * xlag
        xsxs = np.dot(xs.T, xs)
        xsxsi = np.linalg.inv(xsxs)
        xsys = np.dot(xs.T, ys)
        b = np.dot(xsxsi, xsys)

        self.betas = np.vstack((b, self.lam))

        self.u = y - np.dot(self.x, b)
        self.predy = self.y - self.u

        # residual variance

        self.e_filtered = self.u - self.lam * weights.lag_spatial(w, self.u)
        self.sig2 = np.dot(self.e_filtered.T, self.e_filtered) / self.n

        # variance-covariance matrix betas

        varb = self.sig2 * xsxsi

        # variance-covariance matrix lambda, sigma

        a = -self.lam * W
        spfill_diagonal(a, 1.0)
        ai = spinv(a)
        wai = spdot(W, ai)
        tr1 = wai.diagonal().sum()

        wai2 = spdot(wai, wai)
        tr2 = wai2.diagonal().sum()

        waiTwai = spdot(wai.T, wai)
        tr3 = waiTwai.diagonal().sum()

        v1 = np.vstack((tr2 + tr3, tr1 / self.sig2))
        v2 = np.vstack((tr1 / self.sig2, self.n / (2.0 * self.sig2 ** 2)))

        v = np.hstack((v1, v2))

        self.vm1 = np.linalg.inv(v)

        # create variance matrix for beta, lambda
        vv = np.hstack((varb, np.zeros((self.k, 1))))
        vv1 = np.hstack((np.zeros((1, self.k)), self.vm1[0, 0] * np.ones((1, 1))))

        self.vm = np.vstack((vv, vv1))

    def get_x_lag(self, w, regimes_att):
        if regimes_att:
            xlag = weights.lag_spatial(w, regimes_att["x"])
            xlag = REGI.Regimes_Frame.__init__(
                self,
                xlag,
                regimes_att["regimes"],
                constant_regi=None,
                cols2regi=regimes_att["cols2regi"],
            )[0]
            xlag = xlag.toarray()
        else:
            xlag = weights.lag_spatial(w, self.x)
        return xlag


class ML_Error(BaseML_Error):

    """
    ML estimation of the spatial error model with all results and diagnostics;
    :cite:`Anselin1988`

    Parameters
    ----------
    y            : numpy.ndarray or pandas.Series
                   nx1 array for dependent variable
    x            : numpy.ndarray or pandas object
                   Two dimensional array with n rows and one column for each
                   independent (exogenous) variable, excluding the constant
    w            : Sparse matrix
                   Spatial weights sparse matrix
    slx_lags     : integer
                   Number of spatial lags of X to include in the model specification.
                   If slx_lags>0, the specification becomes of the SLX-Error type. 
    slx_vars     : either "All" (default) or list of booleans to select x variables
                   to be lagged
    regimes      : list or pandas.Series
                   List of n values with the mapping of each
                   observation to a regime. Assumed to be aligned with 'x'.
                   For other regimes-specific arguments, see ML_Error_Regimes
    method       : string
                   if 'full', brute force calculation (full matrix expressions)
                   if 'ord', Ord eigenvalue method
                   if 'LU', LU sparse matrix decomposition
    epsilon      : float
                   tolerance criterion in mimimize_scalar function and inverse_product
    vm           : boolean
                   if True, include variance-covariance matrix in summary
                   results
    name_y       : string
                   Name of dependent variable for use in output
    name_x       : list of strings
                   Names of independent variables for use in output
    name_w       : string
                   Name of weights matrix for use in output
    name_ds      : string
                   Name of dataset for use in output
    latex        : boolean
                   Specifies if summary is to be printed in latex format

    Attributes
    ----------
    output       : dataframe
                   regression results pandas dataframe
    betas        : array
                   (k+1)x1 array of estimated coefficients (rho first)
    lam          : float
                   estimate of spatial autoregressive coefficient
    u            : array
                   nx1 array of residuals
    e_filtered   : array
                   nx1 array of spatially filtered residuals
    predy        : array
                   nx1 array of predicted y values
    n            : integer
                   Number of observations
    k            : integer
                   Number of variables for which coefficients are estimated
                   (including the constant, excluding lambda)
    y            : array
                   nx1 array for dependent variable
    x            : array
                   Two dimensional array with n rows and one column for each
                   independent (exogenous) variable, including the constant
    method       : string
                   log Jacobian method
                   if 'full': brute force (full matrix computations)
    epsilon      : float
                   tolerance criterion used in minimize_scalar function and inverse_product
    mean_y       : float
                   Mean of dependent variable
    std_y        : float
                   Standard deviation of dependent variable
    varb         : array
                   Variance covariance matrix (k+1 x k+1) - includes var(lambda)
    vm1          : array
                   variance covariance matrix for lambda, sigma (2 x 2)
    sig2         : float
                   Sigma squared used in computations
    logll        : float
                   maximized log-likelihood (including constant terms)
    pr2          : float
                   Pseudo R squared (squared correlation between y and ypred)
    utu          : float
                   Sum of squared residuals
    std_err      : array
                   1xk array of standard errors of the betas
    z_stat       : list of tuples
                   z statistic; each tuple contains the pair (statistic,
                   p-value), where each is a float
    name_y       : string
                   Name of dependent variable for use in output
    name_x       : list of strings
                   Names of independent variables for use in output
    name_w       : string
                   Name of weights matrix for use in output
    name_ds      : string
                   Name of dataset for use in output
    title        : string
                   Name of the regression method used

    Examples
    --------

    >>> import numpy as np
    >>> import libpysal
    >>> from libpysal.examples import load_example
    >>> from libpysal.weights import Queen
    >>> from spreg import ML_Error
    >>> np.set_printoptions(suppress=True) #prevent scientific format
    >>> south = load_example('South')
    >>> db = libpysal.io.open(south.get_path("south.dbf"),'r')
    >>> y_name = "HR90"
    >>> y = np.array(db.by_col(y_name))
    >>> y.shape = (len(y),1)
    >>> x_names = ["RD90","PS90","UE90","DV90"]
    >>> x = np.array([db.by_col(var) for var in x_names]).T
    >>> w = Queen.from_shapefile(south.get_path("south.shp"))
    >>> w_name = "south_q.gal"
    >>> w.transform = 'r'
    >>> mlerr = ML_Error(y,x,w,name_y=y_name,name_x=x_names,\
               name_w=w_name,name_ds=ds_name) #doctest: +SKIP
    >>> np.around(mlerr.betas, decimals=4) #doctest: +SKIP
    array([[ 6.1492],
           [ 4.4024],
           [ 1.7784],
           [-0.3781],
           [ 0.4858],
           [ 0.2991]])
    >>> "{0:.4f}".format(mlerr.lam) #doctest: +SKIP
    '0.2991'
    >>> "{0:.4f}".format(mlerr.mean_y) #doctest: +SKIP
    '9.5493'
    >>> "{0:.4f}".format(mlerr.std_y) #doctest: +SKIP
    '7.0389'
    >>> np.around(np.diag(mlerr.vm), decimals=4) #doctest: +SKIP
    array([ 1.0648,  0.0555,  0.0454,  0.0061,  0.0148,  0.0014])
    >>> np.around(mlerr.sig2, decimals=4) #doctest: +SKIP
    array([[ 32.4069]])
    >>> "{0:.4f}".format(mlerr.logll) #doctest: +SKIP
    '-4471.4071'
    >>> "{0:.4f}".format(mlerr.aic) #doctest: +SKIP
    '8952.8141'
    >>> "{0:.4f}".format(mlerr.schwarz) #doctest: +SKIP
    '8979.0779'
    >>> "{0:.4f}".format(mlerr.pr2) #doctest: +SKIP
    '0.3058'
    >>> "{0:.4f}".format(mlerr.utu) #doctest: +SKIP
    '48534.9148'
    >>> np.around(mlerr.std_err, decimals=4) #doctest: +SKIP
    array([ 1.0319,  0.2355,  0.2132,  0.0784,  0.1217,  0.0378])
    >>> np.around(mlerr.z_stat, decimals=4) #doctest: +SKIP
    array([[  5.9593,   0.    ],
           [ 18.6902,   0.    ],
           [  8.3422,   0.    ],
           [ -4.8233,   0.    ],
           [  3.9913,   0.0001],
           [  7.9089,   0.    ]])
    >>> mlerr.name_y #doctest: +SKIP
    'HR90'
    >>> mlerr.name_x #doctest: +SKIP
    ['CONSTANT', 'RD90', 'PS90', 'UE90', 'DV90', 'lambda']
    >>> mlerr.name_w #doctest: +SKIP
    'south_q.gal'
    >>> mlerr.name_ds #doctest: +SKIP
    'south.dbf'
    >>> mlerr.title #doctest: +SKIP
    'MAXIMUM LIKELIHOOD SPATIAL ERROR (METHOD = FULL)'


    """

    def __init__(
        self,
        y,
        x,
        w,
        slx_lags=0,
        slx_vars="All",
        regimes=None,
        method="full",
        epsilon=0.0000001,
        vm=False,
        name_y=None,
        name_x=None,
        name_w=None,
        name_ds=None,
        latex=False,
        **kwargs
    ):
        if regimes is not None:
            from .ml_error_regimes import ML_Error_Regimes
            self.__class__ = ML_Error_Regimes
            self.__init__(
                y=y,
                x=x,
                regimes=regimes,
                w=w,
                slx_lags=slx_lags,
                method=method,
                epsilon=epsilon,
                vm=vm,
                name_y=name_y,
                name_x=name_x,
                name_w=name_w,
                name_ds=name_ds,
                latex=latex,
                **kwargs,
            )
        else:        
            n = USER.check_arrays(y, x)
            y, name_y = USER.check_y(y, n, name_y)
            w = USER.check_weights(w, y, w_required=True, slx_lags=slx_lags)
            x_constant, name_x, warn = USER.check_constant(x, name_x)
            name_x = USER.set_name_x(name_x, x_constant) # initialize in case None includes constant
            set_warn(self, warn)
            self.title = "ML SPATIAL ERROR"
            if slx_lags >0:
            #    lag_x = get_lags(w, x_constant[:, 1:], slx_lags)
            #    x_constant = np.hstack((x_constant, lag_x))
    #            name_x += USER.set_name_spatial_lags(name_x, slx_lags)
            #    name_x += USER.set_name_spatial_lags(name_x[1:], slx_lags) # exclude constant from name_x
                x_constant,name_x = USER.flex_wx(w,x=x_constant,name_x=name_x,constant=True,
                                                slx_lags=slx_lags,slx_vars=slx_vars)
                self.title += " WITH SLX (SLX-Error)"
            self.title += " (METHOD = " + method + ")"

            method = method.upper()
            BaseML_Error.__init__(
                self, y=y, x=x_constant, w=w, method=method, epsilon=epsilon
            )
            self.name_ds = USER.set_name_ds(name_ds)
            self.name_y = USER.set_name_y(name_y)
            self.name_x = name_x
            self.name_x.append("lambda")
            self.name_w = USER.set_name_w(name_w, w)
            self.aic = DIAG.akaike(reg=self)
            self.schwarz = DIAG.schwarz(reg=self)
            self.output = pd.DataFrame(self.name_x, columns=['var_names'])
            self.output['var_type'] = ['o'] + ['x'] * (len(self.name_x)-2) + ['lambda']
            self.output['regime'], self.output['equation'] = (0, 0)
            self.other_top = _nonspat_top(self, ml=True)
            output(reg=self, vm=vm, robust=False, other_end=False, latex=latex)


def err_c_loglik(lam, n, y, ylag, x, xlag, W):
    # concentrated log-lik for error model, no constants, brute force
    ys = y - lam * ylag
    xs = x - lam * xlag
    ysys = np.dot(ys.T, ys)
    xsxs = np.dot(xs.T, xs)
    xsxsi = np.linalg.inv(xsxs)
    xsys = np.dot(xs.T, ys)
    x1 = np.dot(xsxsi, xsys)
    x2 = np.dot(xsys.T, x1)
    ee = ysys - x2
    sig2 = ee[0][0] / n
    nlsig2 = (n / 2.0) * np.log(sig2)
    a = -lam * W
    np.fill_diagonal(a, 1.0)
    jacob = np.log(np.linalg.det(a))
    # this is the negative of the concentrated log lik for minimization
    clik = nlsig2 - jacob
    return clik


def err_c_loglik_sp(lam, n, y, ylag, x, xlag, I, Wsp):
    # concentrated log-lik for error model, no constants, LU
    if isinstance(lam, np.ndarray):
        if lam.shape == (1, 1):
            lam = lam[0][0]  # why does the interior value change?
    ys = y - lam * ylag
    xs = x - lam * xlag
    ysys = np.dot(ys.T, ys)
    xsxs = np.dot(xs.T, xs)
    xsxsi = np.linalg.inv(xsxs)
    xsys = np.dot(xs.T, ys)
    x1 = np.dot(xsxsi, xsys)
    x2 = np.dot(xsys.T, x1)
    ee = ysys - x2
    sig2 = ee[0][0] / n
    nlsig2 = (n / 2.0) * np.log(sig2)
    a = I - lam * Wsp
    LU = SuperLU(a.tocsc())
    jacob = np.sum(np.log(np.abs(LU.U.diagonal())))
    # this is the negative of the concentrated log lik for minimization
    clik = nlsig2 - jacob
    return clik


def err_c_loglik_ord(lam, n, y, ylag, x, xlag, evals):
    # concentrated log-lik for error model, no constants, eigenvalues
    ys = y - lam * ylag
    xs = x - lam * xlag
    ysys = np.dot(ys.T, ys)
    xsxs = np.dot(xs.T, xs)
    xsxsi = np.linalg.inv(xsxs)
    xsys = np.dot(xs.T, ys)
    x1 = np.dot(xsxsi, xsys)
    x2 = np.dot(xsys.T, x1)
    ee = ysys - x2
    sig2 = ee[0][0] / n
    nlsig2 = (n / 2.0) * np.log(sig2)
    revals = lam * evals
    jacob = np.log(1 - revals).sum()
    if isinstance(jacob, complex):
        jacob = jacob.real
    # this is the negative of the concentrated log lik for minimization
    clik = nlsig2 - jacob
    return clik


def _test():
    import doctest

    start_suppress = np.get_printoptions()["suppress"]
    np.set_printoptions(suppress=True)
    doctest.testmod()
    np.set_printoptions(suppress=start_suppress)

if __name__ == "__main__":
    _test()

    import numpy as np
    import libpysal

    db = libpysal.io.open(libpysal.examples.get_path("columbus.dbf"), "r")
    y_var = "CRIME"
    y = np.array([db.by_col(y_var)]).reshape(49, 1)
    x_var = ["INC"]
    x = np.array([db.by_col(name) for name in x_var]).T
    w = libpysal.weights.Rook.from_shapefile(libpysal.examples.get_path("columbus.shp"))
    w.transform = "r"
    model = ML_Error(
        y,
        x,
        w=w,
        vm=False,
        name_y=y_var,
        name_x=x_var,
        name_ds="columbus",
        name_w="columbus.gal",
    )
    print(model.output)
    print(model.summary)
