# This file is part of pycam02ucs
# Copyright (C) 2014-2015 Nathaniel Smith <njs@pobox.com>
# See file LICENSE.txt for license information.

# Basic colorspaces: conversions between sRGB, XYZ, xyY, CIELAB

import numpy as np

from .illuminants import as_XYZ100_w
from .testing import check_conversion

################################################################
# sRGB <-> sRGB-linear <-> XYZ100
################################################################

# https://en.wikipedia.org/wiki/SRGB#The_reverse_transformation
def C_linear(C_srgb):
    out = np.empty(C_srgb.shape, dtype=float)
    linear_portion = (C_srgb < 0.04045)
    a = 0.055
    out[linear_portion] = C_srgb[linear_portion] / 12.92
    out[~linear_portion] = ((C_srgb[~linear_portion] + a) / (a + 1)) ** 2.4
    return out

def C_srgb(C_linear):
    out = np.empty(C_linear.shape, dtype=float)
    linear_portion = (C_linear <= 0.0031308)
    a = 0.055
    out[linear_portion] = C_linear[linear_portion] * 12.92
    out[~linear_portion] = (1+a) * C_linear[~linear_portion] ** (1/2.4) - a
    return out

XYZ100_to_sRGB_matrix = np.array([
    # This is the exact matrix specified in IEC 61966-2-1:1999
    [ 3.2406, -1.5372, -0.4986],
    [-0.9689,  1.8758,  0.0415],
    [ 0.0557, -0.2040,  1.0570],
    ])

# Condition number is 4.3, inversion is safe:
sRGB_to_XYZ100_matrix = np.linalg.inv(XYZ100_to_sRGB_matrix)

def XYZ100_to_sRGB_linear(XYZ100):
    """Convert XYZ to linear sRGB, where XYZ is normalized so that reference
    white D65 is X=95.05, Y=100, Z=108.90. Linear sRGB has a linear
    relationship to actual light, so it is an appropriate space for simulating
    light (e.g. for alpha blending).

    """
    XYZ100 = np.asarray(XYZ100, dtype=float)
    # this is broadcasting matrix * array-of-vectors, where the vector is the
    # last dim
    RGB_linear = np.einsum("...ij,...j->...i", XYZ100_to_sRGB_matrix, XYZ100 / 100)
    return RGB_linear

def sRGB_linear_to_sRGB(sRGB_linear):
    return C_srgb(np.asarray(sRGB_linear, dtype=float))

def sRGB_to_sRGB_linear(sRGB):
    """Convert sRGB (as floats in the 0-to-1 range) to linear sRGB."""
    sRGB = np.asarray(sRGB, dtype=float)
    sRGB_linear = C_linear(sRGB)
    return sRGB_linear

def sRGB_linear_to_XYZ100(sRGB_linear):
    sRGB_linear = np.asarray(sRGB_linear, dtype=float)
    # this is broadcasting matrix * array-of-vectors, where the vector is the
    # last dim
    XYZ100 = np.einsum("...ij,...j->...i", sRGB_to_XYZ100_matrix, sRGB_linear)
    XYZ100 *= 100
    return XYZ100

def test_sRGB_to_sRGB_linear():
    from .gold_values import sRGB_sRGB_linear_gold
    check_conversion(sRGB_to_sRGB_linear, sRGB_linear_to_sRGB,
                     sRGB_sRGB_linear_gold,
                     a_max=1, b_max=1)

def test_sRGB_linear_to_XYZ100():
    from .gold_values import sRGB_linear_XYZ100_gold
    check_conversion(sRGB_linear_to_XYZ100, XYZ100_to_sRGB_linear,
                      sRGB_linear_XYZ100_gold,
                      a_max=1, b_max=100)

################################################################
# XYZ100 <-> xyY100
################################################################

def XYZ100_to_xyY100(XYZ100):
    XYZ100 = np.asarray(XYZ100, dtype=float)
    norm = np.sum(XYZ100, axis=-1, keepdims=True)
    xy = XYZ100[..., :2] / norm
    return np.concatenate((xy, XYZ100[..., 1:2]), axis=-1)

def xyY100_to_XYZ100(xyY100):
    xyY100 = np.asarray(xyY100, dtype=float)
    x = xyY100[..., 0]
    y = xyY100[..., 1]
    Y = xyY100[..., 2]
    X = Y / y * x
    Z = Y / y * (1 - x - y)
    return np.concatenate((X[..., np.newaxis],
                           Y[..., np.newaxis],
                           Z[..., np.newaxis]),
                          axis=-1)

_XYZ100_to_xyY100_test_vectors = [
    ([10, 20, 30], [ 10. / 60,  20. / 60, 20]),
    ([99, 98,  3], [99. / 200, 98. / 200, 98]),
    ]

def test_XYZ100_to_xyY100():
    check_conversion(XYZ100_to_xyY100, xyY100_to_XYZ100,
                      _XYZ100_to_xyY100_test_vectors, b_max=[1, 1, 100])

################################################################
# XYZ100 <-> CIEL*a*b*
################################################################

# https://en.wikipedia.org/wiki/Lab_color_space#CIELAB-CIEXYZ_conversions
def _f(t):
    out = np.empty(t.shape, dtype=float)
    linear_portion = (t < (6. / 29) ** 3)
    out[linear_portion] = ((1. / 3) * (29. / 6) ** 2 * t[linear_portion]
                           + 4. / 29)
    out[~linear_portion] = t[~linear_portion] ** (1. / 3)
    return out

def XYZ100_to_CIELAB(XYZ100, XYZ100_w):
    XYZ100 = np.asarray(XYZ100, dtype=float)
    XYZ100_w = as_XYZ100_w(XYZ100_w)

    fXYZ100_norm = _f(XYZ100 / XYZ100_w)
    L = 116 * fXYZ100_norm[..., 1:2] - 16
    a = 500 * (fXYZ100_norm[..., 0:1] - fXYZ100_norm[..., 1:2])
    b = 200 * (fXYZ100_norm[..., 1:2] - fXYZ100_norm[..., 2:3])
    return np.concatenate((L, a, b), axis=-1)

def _finv(t):
    linear_portion = (t <= 6. / 29)
    out = np.select([linear_portion, ~linear_portion],
                    [3 * (6. / 29) ** 2 * (t - 4. / 29),
                     t ** 3])
    return out

def CIELAB_to_XYZ100(CIELAB, XYZ100_w):
    CIELAB = np.asarray(CIELAB, dtype=float)
    XYZ100_w = as_XYZ100_w(XYZ100_w)

    L = CIELAB[..., 0]
    a = CIELAB[..., 1]
    b = CIELAB[..., 2]
    X_w = XYZ100_w[..., 0]
    Y_w = XYZ100_w[..., 1]
    Z_w = XYZ100_w[..., 2]

    l_piece = 1. / 116 * (L + 16)
    X = X_w * _finv(l_piece + 1. / 500 * a)
    Y = Y_w * _finv(l_piece)
    Z = Z_w * _finv(l_piece - 1. / 200 * b)

    return np.concatenate((X[..., np.newaxis],
                           Y[..., np.newaxis],
                           Z[..., np.newaxis]),
                          axis=-1)

def test_XYZ100_to_CIELAB():
    from .gold_values import XYZ100_CIELAB_gold_D65, XYZ100_CIELAB_gold_D50

    check_conversion(XYZ100_to_CIELAB, CIELAB_to_XYZ100,
                     XYZ100_CIELAB_gold_D65,
                     # Stick to randomized values in the mid-range to avoid
                     # hitting negative luminances
                     b_min=[10, -30, -30], b_max=[90, 30, 30],
                     XYZ100_w="D65")

    check_conversion(XYZ100_to_CIELAB, CIELAB_to_XYZ100,
                     XYZ100_CIELAB_gold_D50,
                     # Stick to randomized values in the mid-range to avoid
                     # hitting negative luminances
                     b_min=[10, -30, -30], b_max=[90, 30, 30],
                     XYZ100_w="D50")

    XYZ1001 = np.asarray(XYZ100_CIELAB_gold_D65[0][0])
    CIELAB1 = np.asarray(XYZ100_CIELAB_gold_D65[0][1])

    XYZ1002 = np.asarray(XYZ100_CIELAB_gold_D50[1][0])
    CIELAB2 = np.asarray(XYZ100_CIELAB_gold_D50[1][1])

    XYZ100_mixed = np.concatenate((XYZ1001[np.newaxis, :],
                                   XYZ1002[np.newaxis, :]))
    CIELAB_mixed = np.concatenate((CIELAB1[np.newaxis, :],
                                   CIELAB2[np.newaxis, :]))
    XYZ100_w_mixed = np.row_stack((as_XYZ100_w("D65"), as_XYZ100_w("D50")))

    assert np.allclose(XYZ100_to_CIELAB(XYZ100_mixed, XYZ100_w=XYZ100_w_mixed),
                       CIELAB_mixed, rtol=0.001)
    assert np.allclose(CIELAB_to_XYZ100(CIELAB_mixed, XYZ100_w=XYZ100_w_mixed),
                       XYZ100_mixed, rtol=0.001)