import os
import numpy as np
import nibabel as nib
import matplotlib.pyplot as plt
import math
import warnings
from scipy.spatial import distance
from skimage import measure
import cv2
from collections import defaultdict
from numpy.linalg import norm
from scipy.interpolate import splprep, splev
from scipy.ndimage.morphology import binary_closing as closing
from skimage.morphology import skeletonize
from collections import Counter
from skimage.measure import label
import pandas as pd
from scipy.interpolate import interp1d
from scipy.signal import savgol_filter
from scipy.signal import argrelextrema


def getLargestCC(segmentation):
    nb_labels = np.unique(segmentation)[1:]
    out_image = np.zeros_like(segmentation)
    for ncc in nb_labels:
        _aux = np.squeeze(segmentation == ncc).astype(float)  # get myocardial labe
        labels = label(_aux)
        assert (labels.max() != 0)  # assume at least 1 CC
        largestCC = labels == np.argmax(np.bincount(labels.flat)[1:]) + 1
        out_image += largestCC * ncc
    return out_image


def binarymatrix(A):
    A_aux = np.copy(A)
    A = map(tuple, A)
    dic = Counter(A)
    for (i, j) in dic.items():
        if j > 1:
            ind = np.where(((A_aux[:, 0] == i[0]) & (A_aux[:, 1] == i[1])))[0]
            A_aux = np.delete(A_aux, ind[1:], axis=0)
    if np.linalg.norm(A_aux[:, 0] - A_aux[:, -1]) < 0.01:
        A_aux = A_aux[:-1, :]
    return A_aux


def get_right_atrial_volumes(seg, _seq, _fr, _pointsRV, dx, dy):
    """
    This function gets the centre line (height) of the atrium and atrial dimension at 15 points along this line.
    """
    _apex_RV_img, _rvlv_point_img, _free_rv_point_img = _pointsRV

    _apex_RV = [_apex_RV_img[0]*dy,_apex_RV_img[1]*dx]
    _rvlv_point = [_rvlv_point_img[0]*dy,_rvlv_point_img[1]*dx]
    _free_rv_point = [_free_rv_point_img[0]*dy,_free_rv_point_img[1]*dx]


    if debug:
        plt.figure()
        plt.imshow(seg)
        plt.plot(_apex_RV[1]/dx, _apex_RV[0]/dy, 'mo')
        plt.plot(_rvlv_point[1]/dx, _rvlv_point[0]/dy, 'c*')
        plt.plot(_free_rv_point[1]/dx, _free_rv_point[0]/dy, 'y*')

    mid_valve_RV = np.mean([_rvlv_point, _free_rv_point], axis=0)
    _atria_seg = np.squeeze(seg == 5).astype(float)  # get atria label
    rv_seg = np.squeeze(seg == 3).astype(float)  # get atria label

    # Generate contours from the atria
    _contours_RA_img = measure.find_contours(_atria_seg, 0.8)
    _contours_RA_img = _contours_RA_img[0]

    _contours_RA = np.zeros_like(_contours_RA_img)
    for pts_s in range(len(_contours_RA_img)):
        _contours_RA[pts_s] = [_contours_RA_img[pts_s,0]*dy, _contours_RA_img[pts_s,1]*dx]

    _contours_RV_img = measure.find_contours(rv_seg, 0.8)
    _contours_RV_img = _contours_RV_img[0]
    contours_RV = np.zeros_like(_contours_RV_img)
    for pts_s in range(len(_contours_RV_img)):
        contours_RV[pts_s] = [_contours_RV_img[pts_s,0]*dy, _contours_RV_img[pts_s,1]*dx]

    # Compute distance between mid_valve and every point in contours
    dist = distance.cdist(_contours_RA, [mid_valve_RV])
    ind_mitral_valve = dist.argmin()
    mid_valve_RA = _contours_RA[ind_mitral_valve, :]
    dist = distance.cdist(_contours_RA, [mid_valve_RA])
    ind_top_atria = dist.argmax()
    top_atria = _contours_RA[ind_top_atria, :]
    ind_base1 = distance.cdist(_contours_RA, [_rvlv_point]).argmin()
    ind_base2 = distance.cdist(_contours_RA, [_free_rv_point]).argmin()
    atria_edge1 = _contours_RA[ind_base1, :]
    atria_edge2 = _contours_RA[ind_base2, :]

    if debug:
        plt.figure()
        plt.imshow(seg)
        plt.plot(_contours_RA[:, 1]/dx, _contours_RA[:, 0]/dy, 'r-')
        plt.plot(contours_RV[:, 1]/dx, contours_RV[:, 0]/dy, 'k-')
        plt.plot(top_atria[1]/dx, top_atria[0]/dy, 'mo')
        plt.plot(mid_valve_RA[1]/dx, mid_valve_RA[0]/dy, 'co')
        plt.plot(atria_edge1[1]/dx, atria_edge1[0]/dy, 'go')
        plt.plot(atria_edge2[1]/dx, atria_edge2[0]/dy, 'bo')
        plt.plot(_rvlv_point[1]/dx, _rvlv_point[0]/dy, 'k*')
        plt.plot(_free_rv_point[1]/dx, _free_rv_point[0]/dy, 'b*')

    # Rotate contours by theta degrees
    radians = np.arctan2(np.array((atria_edge1[0] - atria_edge2[0]) / 2),
                         np.array((atria_edge1[1] - atria_edge2[1]) / 2))

    # Rotate contours
    _x = _contours_RA[:, 1]
    y = _contours_RA[:, 0]
    xx_B = _x * math.cos(radians) + y * math.sin(radians)
    yy_B = -_x * math.sin(radians) + y * math.cos(radians)

    # Rotate points
    x_1 = atria_edge1[1]
    y_1 = atria_edge1[0]
    x_2 = atria_edge2[1]
    y_2 = atria_edge2[0]
    x_4 = top_atria[1]
    y_4 = top_atria[0]
    x_5 = mid_valve_RA[1]
    y_5 = mid_valve_RA[0]

    xx_1 = x_1 * math.cos(radians) + y_1 * math.sin(radians)
    yy_1 = -x_1 * math.sin(radians) + y_1 * math.cos(radians)
    xx_2 = x_2 * math.cos(radians) + y_2 * math.sin(radians)
    yy_2 = -x_2 * math.sin(radians) + y_2 * math.cos(radians)
    xx_4 = x_4 * math.cos(radians) + y_4 * math.sin(radians)
    yy_4 = -x_4 * math.sin(radians) + y_4 * math.cos(radians)
    xx_5 = x_5 * math.cos(radians) + y_5 * math.sin(radians)
    yy_5 = -x_5 * math.sin(radians) + y_5 * math.cos(radians)

    # make vertical line through mid_valve_from_atriumcontours_rot
    contours_RA_rot = np.asarray([xx_B, yy_B]).T
    top_atria_rot = np.asarray([xx_4, yy_4])

    # Make more points for the contours.
    intpl_XX = []
    intpl_YY = []
    for ind, coords in enumerate(contours_RA_rot):
        coords1 = coords
        if ind < (len(contours_RA_rot) - 1):
            coords2 = contours_RA_rot[ind + 1]

        else:
            coords2 = contours_RA_rot[0]
        warnings.simplefilter('ignore', np.RankWarning)
        coeff = np.polyfit([coords1[0], coords2[0]], [coords1[1], coords2[1]], 1)
        xx_es = np.linspace(coords1[0], coords2[0], 10)
        intp_val = np.polyval(coeff, xx_es)
        intpl_XX = np.hstack([intpl_XX, xx_es])
        intpl_YY = np.hstack([intpl_YY, intp_val])

    contour_smth = np.vstack([intpl_XX, intpl_YY]).T

    # find the crossing between vert_line and contours_RA_rot.
    dist2 = distance.cdist(contour_smth, [top_atria_rot])
    min_dist2 = np.min(dist2)
    # # step_closer
    newy_atra = top_atria_rot[1] + min_dist2
    new_top_atria = [top_atria_rot[0], newy_atra]
    dist3 = distance.cdist(contour_smth, [new_top_atria])
    ind_min_dist3 = dist3.argmin()

    ind_alt_atria_top = contours_RA_rot[:, 1].argmin()
    final_mid_avalve = np.asarray([xx_5, yy_5])
    final_top_atria = np.asarray([contours_RA_rot[ind_alt_atria_top, 0], contours_RA_rot[ind_alt_atria_top, 1]])
    final_perp_top_atria = contour_smth[ind_min_dist3, :]
    final_atrial_edge1 = np.asarray([xx_1, yy_1])
    final_atrial_edge2 = np.asarray([xx_2, yy_2])

    if debug:
        plt.figure()
        plt.plot(contour_smth[:, 0]/dx, contour_smth[:, 1]/dy, 'r-')
        plt.plot(final_atrial_edge2[0]/dx, final_atrial_edge2[1]/dy, 'y*')
        plt.plot(final_atrial_edge1[0]/dx, final_atrial_edge1[1]/dy, 'm*')
        plt.plot(final_top_atria[0]/dx, final_top_atria[1]/dy, 'c*')
        plt.plot(final_mid_avalve[0]/dx, final_mid_avalve[1]/dy, 'b*')
        plt.title('RA {0}  frame {1}'.format(_seq, _fr))

    alength_top = distance.pdist([final_mid_avalve, final_top_atria])[0]
    alength_perp = distance.pdist([final_mid_avalve, final_perp_top_atria])[0]
    a_segmts = (final_mid_avalve[1] - final_top_atria[1]) / Nsegments_length

    # get length dimension (width) of atrial seg at each place.
    a_diams = np.zeros(Nsegments_length)
    diam1 = abs(np.diff([xx_1, xx_2]))
    points_aux = np.zeros(((Nsegments_length - 1) * 2, 2))
    k = 0
    for ib in range(Nsegments_length):
        if ib == 0:
            a_diams[ib] = diam1
        else:
            vert_y = final_mid_avalve[1] - a_segmts * ib
            rgne_vertY = a_segmts / 6
            min_Y = vert_y - rgne_vertY
            max_Y = vert_y + rgne_vertY
            ind_sel_conts = np.where(np.logical_and(intpl_YY >= min_Y, intpl_YY <= max_Y))[0]

            if len(ind_sel_conts) == 0:
                print('Problem in disk {0}'.format(ib))
                continue

            y_sel_conts = contour_smth[ind_sel_conts, 1]
            x_sel_conts = contour_smth[ind_sel_conts, 0]
            min_ys = np.argmin(np.abs(y_sel_conts - vert_y))

            p1 = ind_sel_conts[min_ys]
            point1 = contour_smth[p1]

            mean_x = np.mean([np.min(x_sel_conts), np.max(x_sel_conts)])
            if mean_x < point1[0]:
                ind_xs = np.where(contour_smth[ind_sel_conts, 0] < mean_x)[0]
                pts = contour_smth[ind_sel_conts[ind_xs], :]
                min_ys = np.argmin(np.abs(pts[:, 1] - vert_y))
                point2 = pts[min_ys]
                a_diam = distance.pdist([point1, point2])[0]
            elif np.min(x_sel_conts) == np.max(x_sel_conts):
                print('{2} Frame {0}, disk {1} diameter is zero'.format(_fr, ib, _seq))
                a_diam = 0
                point2 = np.zeros(2)
                point1 = np.zeros(2)
            else:
                ind_xs = np.where(contour_smth[ind_sel_conts, 0] > mean_x)[0]
                if len(ind_xs) > 0:
                    pts = contour_smth[ind_sel_conts[ind_xs], :]
                    min_ys = np.argmin(np.abs(pts[:, 1] - vert_y))
                    point2 = pts[min_ys]
                    a_diam = distance.pdist([point1, point2])[0]
                else:
                    a_diam = 0
                    point2 = np.zeros(2)
                    point1 = np.zeros(2)
                    print('{2} Frame {0}, disk {0} diameter is zero'.format(_fr, ib, _seq))

            a_diams[ib] = a_diam
            points_aux[k, :] = point1
            points_aux[k + 1, :] = point2

            k += 2

    points_rotate = np.zeros(((Nsegments_length - 1) * 2 + 5, 2))
    points_rotate[0, :] = final_mid_avalve
    points_rotate[1, :] = final_top_atria
    points_rotate[2, :] = final_perp_top_atria
    points_rotate[3, :] = final_atrial_edge1
    points_rotate[4, :] = final_atrial_edge2
    points_rotate[5:, :] = points_aux

    radians2 = 2 * np.pi - radians
    points_non_roatate_ = np.zeros_like(points_rotate)
    for _jj, p in enumerate(points_non_roatate_):
        points_non_roatate_[_jj, 0] = points_rotate[_jj, 0] * math.cos(radians2) + points_rotate[_jj, 1] * math.sin(
            radians2)
        points_non_roatate_[_jj, 1] = -points_rotate[_jj, 0] * math.sin(radians2) + points_rotate[_jj, 1] * math.cos(
            radians2)

    length_apex = distance.pdist([_apex_RV, _free_rv_point])
    if debug:
        plt.close('all')
    return a_diams, alength_top, alength_perp, points_non_roatate_, _contours_RA, length_apex


def get_left_atrial_volumes(seg, _seq, _fr, _points, dx, dy):
    """
    This function gets the centre line (height) of the atrium and atrial dimension at 15 points along this line.
    """
    _apex_img, _mid_valve_img, anterior_2Ch_img, inferior_2Ch_img = _points
    _apex = [_apex_img[0]*dy,_apex_img[1]*dx]
    _mid_valve = [_mid_valve_img[0]*dy,_mid_valve_img[1]*dx]
    anterior_2Ch = [anterior_2Ch_img[0]*dy,anterior_2Ch_img[1]*dx]
    inferior_2Ch = [inferior_2Ch_img[0]*dy,inferior_2Ch_img[1]*dx]

    if debug:
        plt.figure()
        plt.imshow(seg)
        plt.plot(_apex[1]/dx, _apex[0]/dy, 'mo')
        plt.plot(_mid_valve[1]/dx, _mid_valve[0]/dy, 'c*')
        plt.plot(anterior_2Ch[1]/dx, anterior_2Ch[0]/dy, 'y*')
        plt.plot(inferior_2Ch[1]/dx, inferior_2Ch[0]/dy, 'r*')

    if _seq == 'la_2Ch':
        _atria_seg = np.squeeze(seg == 3).astype(float)  # get atria label
    else:
        _atria_seg = np.squeeze(seg == 4).astype(float)  # get atria label

    # Generate contours from the atria
    contours_img = measure.find_contours(_atria_seg, 0.8)
    contours_img = contours_img[0]
    contours = np.zeros_like(contours_img)
    for pts_s in range(len(contours_img)):
        contours[pts_s] = [contours_img[pts_s,0]*dy, contours_img[pts_s,1]*dx]

    # Compute distance between mid_valve and every point in contours
    dist = distance.cdist(contours, [_mid_valve])
    ind_mitral_valve = dist.argmin()
    _mid_valve = contours[ind_mitral_valve, :]
    dist = distance.cdist(contours, [contours[ind_mitral_valve, :]])
    ind_top_atria = dist.argmax()
    top_atria = contours[ind_top_atria, :]
    length_apex_mid_valve = distance.pdist([_apex, _mid_valve])
    length_apex_inferior_2Ch = distance.pdist([_apex, inferior_2Ch])
    length_apex_anterior_2Ch = distance.pdist([_apex, anterior_2Ch])
    lines_LV_ = np.concatenate([length_apex_mid_valve, length_apex_inferior_2Ch, length_apex_anterior_2Ch])
    points_LV_ = np.vstack([_apex, _mid_valve, inferior_2Ch, anterior_2Ch])

    ind_base1 = distance.cdist(contours, [inferior_2Ch]).argmin()
    ind_base2 = distance.cdist(contours, [anterior_2Ch]).argmin()
    atria_edge1 = contours[ind_base1, :]
    atria_edge2 = contours[ind_base2, :]
    # mid valve based on atria
    x_mid_valve_atria = atria_edge1[0] + ((atria_edge2[0] - atria_edge1[0]) / 2)
    y_mid_valve_atria = atria_edge1[1] + ((atria_edge2[1] - atria_edge1[1]) / 2)
    mid_valve_atria = np.array([x_mid_valve_atria, y_mid_valve_atria])
    ind_mid_valve = distance.cdist(contours, [mid_valve_atria]).argmin()
    mid_valve_atria = contours[ind_mid_valve, :]

    if debug:
        plt.figure()
        plt.imshow(seg)
        plt.plot(top_atria[1]/dx, top_atria[0]/dy, 'mo')
        plt.plot(mid_valve_atria[1]/dx, mid_valve_atria[0]/dy, 'c*')
        plt.plot(atria_edge1[1]/dx, atria_edge1[0]/dy, 'y*')
        plt.plot(atria_edge2[1]/dx, atria_edge2[0]/dy, 'r*')

    # Rotate contours by theta degrees
    radians = np.arctan2(np.array((atria_edge2[0] - atria_edge1[0]) / 2),
                         np.array((atria_edge2[1] - atria_edge1[1]) / 2))

    # Rotate contours
    _x = contours[:, 1]
    y = contours[:, 0]
    xx_B = _x * math.cos(radians) + y * math.sin(radians)
    yy_B = -_x * math.sin(radians) + y * math.cos(radians)

    # Rotate points
    x_1 = atria_edge1[1]
    y_1 = atria_edge1[0]
    x_2 = atria_edge2[1]
    y_2 = atria_edge2[0]
    x_4 = top_atria[1]
    y_4 = top_atria[0]
    x_5 = mid_valve_atria[1]
    y_5 = mid_valve_atria[0]

    xx_1 = x_1 * math.cos(radians) + y_1 * math.sin(radians)
    yy_1 = -x_1 * math.sin(radians) + y_1 * math.cos(radians)
    xx_2 = x_2 * math.cos(radians) + y_2 * math.sin(radians)
    yy_2 = -x_2 * math.sin(radians) + y_2 * math.cos(radians)
    xx_4 = x_4 * math.cos(radians) + y_4 * math.sin(radians)
    yy_4 = -x_4 * math.sin(radians) + y_4 * math.cos(radians)
    xx_5 = x_5 * math.cos(radians) + y_5 * math.sin(radians)
    yy_5 = -x_5 * math.sin(radians) + y_5 * math.cos(radians)

    # make vertical line through mid_valve_from_atrium
    contours_rot = np.asarray([xx_B, yy_B]).T
    top_atria_rot = np.asarray([xx_4, yy_4])

    # Make more points for the contours.
    intpl_XX = []
    intpl_YY = []
    for ind, coords in enumerate(contours_rot):
        coords1 = coords
        if ind < (len(contours_rot) - 1):
            coords2 = contours_rot[ind + 1]
        else:
            coords2 = contours_rot[0]
        warnings.simplefilter('ignore', np.RankWarning)
        coeff = np.polyfit([coords1[0], coords2[0]], [coords1[1], coords2[1]], 1)
        xx_es = np.linspace(coords1[0], coords2[0], 10)
        intp_val = np.polyval(coeff, xx_es)
        intpl_XX = np.hstack([intpl_XX, xx_es])
        intpl_YY = np.hstack([intpl_YY, intp_val])

    contour_smth = np.vstack([intpl_XX, intpl_YY]).T

    # find the crossing between vert_line and contours_rot.
    dist2 = distance.cdist(contour_smth, [top_atria_rot])
    min_dist2 = np.min(dist2)
    newy_atra = top_atria_rot[1] + min_dist2
    new_top_atria = [top_atria_rot[0], newy_atra]
    dist3 = distance.cdist(contour_smth, [new_top_atria])
    ind_min_dist3 = dist3.argmin()

    ind_alt_atria_top = contours_rot[:, 1].argmin()
    final_top_atria = np.asarray([contours_rot[ind_alt_atria_top, 0], contours_rot[ind_alt_atria_top, 1]])
    final_perp_top_atria = contour_smth[ind_min_dist3, :]
    final_atrial_edge1 = np.asarray([xx_1, yy_1])
    final_atrial_edge2 = np.asarray([xx_2, yy_2])
    final_mid_avalve = np.asarray([xx_5, yy_5])

    if debug:
        plt.figure()
        plt.plot(contour_smth[:, 0]/dx, contour_smth[:, 1]/dy, 'r-')
        plt.plot(final_atrial_edge2[0]/dx, final_atrial_edge2[1]/dy, 'y*')
        plt.plot(final_atrial_edge1[0]/dx, final_atrial_edge1[1]/dy, 'm*')
        plt.plot(final_perp_top_atria[0]/dx, final_perp_top_atria[1]/dy, 'ko')
        plt.plot(final_top_atria[0]/dx, final_top_atria[1]/dy, 'c*')
        plt.plot(new_top_atria[0]/dx, new_top_atria[1]/dy, 'g*')
        plt.plot(final_mid_avalve[0]/dx, final_mid_avalve[1]/dy, 'b*')
        plt.title('LA {0}  frame {1}'.format(_seq, _fr))

    # now find length of atrium divide in the  15 segments
    alength_top = distance.pdist([final_mid_avalve, final_top_atria])[0]
    alength_perp = distance.pdist([final_mid_avalve, final_perp_top_atria])[0]
    a_segmts = (final_mid_avalve[1] - final_top_atria[1]) / Nsegments_length

    a_diams = np.zeros(Nsegments_length)
    diam1 = abs(np.diff([xx_1, xx_2]))
    points_aux = np.zeros(((Nsegments_length - 1) * 2, 2))
    k = 0
    for ib in range(Nsegments_length):
        if ib == 0:
            a_diams[ib] = diam1
        else:
            vert_y = final_mid_avalve[1] - a_segmts * ib
            rgne_vertY = a_segmts / 6
            min_Y = vert_y - rgne_vertY
            max_Y = vert_y + rgne_vertY
            ind_sel_conts = np.where(np.logical_and(intpl_YY >= min_Y, intpl_YY <= max_Y))[0]

            if len(ind_sel_conts) == 0:
                print('Problem in disk {0}'.format(ib))
                continue

            y_sel_conts = contour_smth[ind_sel_conts, 1]
            x_sel_conts = contour_smth[ind_sel_conts, 0]
            min_ys = np.argmin(np.abs(y_sel_conts - vert_y))

            p1 = ind_sel_conts[min_ys]
            point1 = contour_smth[p1]

            mean_x = np.mean([np.min(x_sel_conts), np.max(x_sel_conts)])
            if mean_x < point1[0]:
                ind_xs = np.where(contour_smth[ind_sel_conts, 0] < mean_x)[0]
                pts = contour_smth[ind_sel_conts[ind_xs], :]
                min_ys = np.argmin(np.abs(pts[:, 1] - vert_y))
                point2 = pts[min_ys]
                a_diam = distance.pdist([point1, point2])[0]

            elif np.min(x_sel_conts) == np.max(x_sel_conts):
                print('{2} Frame {0}, disk {1} diameter is zero'.format(_fr, ib, _seq))
                a_diam = 0
                point2 = np.zeros(2)
                point1 = np.zeros(2)
            else:
                ind_xs = np.where(contour_smth[ind_sel_conts, 0] > mean_x)[0]
                if len(ind_xs) > 0:
                    pts = contour_smth[ind_sel_conts[ind_xs], :]
                    min_ys = np.argmin(np.abs(pts[:, 1] - vert_y))
                    point2 = pts[min_ys]
                    a_diam = distance.pdist([point1, point2])[0]

                else:
                    a_diam = 0
                    point2 = np.zeros(2)
                    point1 = np.zeros(2)
                    print('{2} Frame {0}, disk {0} diameter is zero'.format(_fr, ib, _seq))

            a_diams[ib] = a_diam
            points_aux[k, :] = point1
            points_aux[k + 1, :] = point2

            k += 2

    points_rotate = np.zeros(((Nsegments_length - 1) * 2 + 5, 2))
    points_rotate[0, :] = final_mid_avalve
    points_rotate[1, :] = final_top_atria
    points_rotate[2, :] = final_perp_top_atria
    points_rotate[3, :] = final_atrial_edge1
    points_rotate[4, :] = final_atrial_edge2
    points_rotate[5:, :] = points_aux

    radians2 = 2 * np.pi - radians
    points_non_roatate_ = np.zeros_like(points_rotate)
    for _jj, p in enumerate(points_non_roatate_):
        points_non_roatate_[_jj, 0] = points_rotate[_jj, 0] * math.cos(radians2) + points_rotate[_jj, 1] * math.sin(
            radians2)
        points_non_roatate_[_jj, 1] = -points_rotate[_jj, 0] * math.sin(radians2) + points_rotate[_jj, 1] * math.cos(
            radians2)
    if debug:
        plt.close('all')
    return a_diams, alength_top, alength_perp, points_non_roatate_, contours, lines_LV_, points_LV_


def detect_LV_points(seg):
    myo_seg = np.squeeze(seg == 2).astype(float)
    kernel = np.ones((2, 2), np.uint8)
    myo_seg_dil = cv2.dilate(myo_seg, kernel, iterations=2)
    myo2 = get_processed_myocardium(myo_seg_dil, _label=1)
    cl_pts, _mid_valve = get_sorted_sk_pts(myo2)
    dist_myo = distance.cdist(cl_pts, [_mid_valve])
    ind_apex = dist_myo.argmax()
    _apex = cl_pts[ind_apex, :]
    _septal_mv = cl_pts[0, 0], cl_pts[0, 1]
    _ant_mv = cl_pts[-1, 0], cl_pts[-1, 1]

    return np.asarray(_apex), np.asarray(_mid_valve), np.asarray(_septal_mv), np.asarray(_ant_mv)


def get_processed_myocardium(seg, _label=2):
    """
    This function tidies the LV myocardial segmentation, taking only the single
    largest connected component, and performing an opening (erosion+dilation)
    """

    myo_aux = np.squeeze(seg == _label).astype(float)  # get myocardial label
    myo_aux = closing(myo_aux, structure=np.ones((2, 2))).astype(float)
    cc_aux = measure.label(myo_aux, connectivity=1)
    ncc_aux = len(np.unique(cc_aux))

    if not ncc_aux <= 1:
        cc_counts, cc_inds = np.histogram(cc_aux, range(ncc_aux + 1))
        cc_inds = cc_inds[:-1]
        cc_inds_sorted = [_x for (y, _x) in sorted(zip(cc_counts, cc_inds))]
        biggest_cc_ind = cc_inds_sorted[-2]  # Take second largest CC (after background)
        myo_aux = closing(myo_aux, structure=np.ones((2, 2))).astype(float)

        # Take largest connected component
        if not (len(np.where(cc_aux > 0)[0]) == len(np.where(cc_aux == biggest_cc_ind)[0])):
            mask = cc_aux == biggest_cc_ind
            myo_aux *= mask
            myo_aux = closing(myo_aux).astype(float)

    return myo_aux


def get_sorted_sk_pts(myo, n_samples=48, centroid=np.array([0, 0])):
    #   ref -       reference start point for spline point ordering
    #   n_samples  output number of points for sampling spline

    # check for side branches? need connectivity check
    sk_im = skeletonize(myo)

    myo_pts = np.asarray(np.nonzero(myo)).transpose()
    sk_pts = np.asarray(np.nonzero(sk_im)).transpose()

    # convert to radial coordinates and sort circumferential
    if centroid[0] == 0 and centroid[1] == 0:
        centroid = np.mean(sk_pts, axis=0)

    # get skeleton consisting only of longest path
    sk_im = get_longest_path(sk_im)

    # sort centreline points based from boundary points at valves as start
    # and end point. Make ref point out of LV through valve
    out = skeleton_endpoints(sk_im.astype(int))
    end_pts = np.asarray(np.nonzero(out)).transpose()
    sk_pts = np.asarray(np.nonzero(sk_im)).transpose()

    if len(end_pts) > 2:
        print('Error! More than 2 end-points in LA myocardial skeleton.')
        cl_pts = []
        _mid_valve = []
        return cl_pts, _mid_valve
    else:
        # set reference to vector pointing from centroid to mid-valve
        _mid_valve = np.mean(end_pts, axis=0)
        ref = (_mid_valve - centroid) / norm(_mid_valve - centroid)
        sk_pts2 = sk_pts - centroid  # centre around centroid
        myo_pts2 = myo_pts - centroid
        theta = np.zeros([len(sk_pts2), ])
        theta_myo = np.zeros([len(myo_pts2), ])

        eps = 0.0001
        if len(sk_pts2) <= 5:
            print('Skeleton failed! Only of length {}'.format(len(sk_pts2)))
            cl_pts = []
            _mid_valve = []
            return cl_pts, _mid_valve
        else:
            # compute angle theta for skeleton points
            for k, ss in enumerate(sk_pts2):
                if (np.dot(ref, ss) / norm(ss) < 1.0 + eps) and (np.dot(ref, ss) / norm(ss) > 1.0 - eps):
                    theta[k] = 0
                elif (np.dot(ref, ss) / norm(ss) < -1.0 + eps) and (np.dot(ref, ss) / norm(ss) > -1.0 - eps):
                    theta[k] = 180
                else:
                    theta[k] = math.acos(np.dot(ref, ss) / norm(ss)) * 180 / np.pi
                detp = ref[0] * ss[1] - ref[1] * ss[0]
                if detp > 0:
                    theta[k] = 360 - theta[k]
            thinds = theta.argsort()
            sk_pts = sk_pts[thinds, :].astype(float)  # ordered centreline points

            # # compute angle theta for myo points
            for k, ss in enumerate(myo_pts2):
                # compute angle theta
                eps = 0.0001
                if (np.dot(ref, ss) / norm(ss) < 1.0 + eps) and (np.dot(ref, ss) / norm(ss) > 1.0 - eps):
                    theta_myo[k] = 0
                elif (np.dot(ref, ss) / norm(ss) < -1.0 + eps) and (np.dot(ref, ss) / norm(ss) > -1.0 - eps):
                    theta_myo[k] = 180
                else:
                    theta_myo[k] = math.acos(np.dot(ref, ss) / norm(ss)) * 180 / np.pi
                detp = ref[0] * ss[1] - ref[1] * ss[0]
                if detp > 0:
                    theta_myo[k] = 360 - theta_myo[k]
            # sub-sample and order myo points circumferential
            theta_myo.sort()

            # Remove duplicates
            sk_pts = binarymatrix(sk_pts)
            # fit b-spline curve to skeleton, sample fixed number of points
            tck, u = splprep(sk_pts.T, s=10.0, nest=-1, quiet=2)
            u_new = np.linspace(u.min(), u.max(), n_samples)
            cl_pts = np.zeros([n_samples, 2])
            cl_pts[:, 0], cl_pts[:, 1] = splev(u_new, tck)

            # get centreline theta
            cl_theta = np.zeros([len(cl_pts), ])
            cl_pts2 = cl_pts - centroid  # centre around centroid
            for k, ss in enumerate(cl_pts2):
                # compute angle theta
                if (np.dot(ref, ss) / norm(ss) < 1.0 + eps) and (np.dot(ref, ss) / norm(ss) > 1.0 - eps):
                    cl_theta[k] = 0
                else:
                    cl_theta[k] = math.acos(np.dot(ref, ss) / norm(ss)) * 180 / np.pi
                detp = ref[0] * ss[1] - ref[1] * ss[0]
                if detp > 0:
                    cl_theta[k] = 360 - cl_theta[k]
            cl_theta.sort()
            return cl_pts, _mid_valve


def get_longest_path(skel):
    # first create edges from skeleton
    sk_im = skel.copy()
    # remove bad (L-shaped) junctions
    sk_im = remove_bad_junctions(sk_im)

    # get seeds for longest path from existing end-points
    out = skeleton_endpoints(sk_im.astype(int))
    end_pts = np.asarray(np.nonzero(out)).transpose()
    if len(end_pts) == 0:
        print('ERROR! No end-points detected! Exiting.')
    # break
    elif len(end_pts) == 1:
        print('Warning! Only 1 end-point detected!')
    elif len(end_pts) > 2:
        print('Warning! {0} end-points detected!'.format(len(end_pts)))

    sk_pts = np.asarray(np.nonzero(sk_im)).transpose()
    # search indices of sk_pts for end points
    tmp_inds = np.ravel_multi_index(sk_pts.T, (np.max(sk_pts[:, 0]) + 1, np.max(sk_pts[:, 1]) + 1))
    seed_inds = np.zeros((len(end_pts), 1))
    for i, e in enumerate(end_pts):
        seed_inds[i] = int(
            np.where(tmp_inds == np.ravel_multi_index(e.T, (np.max(sk_pts[:, 0]) + 1, np.max(sk_pts[:, 1]) + 1)))[0])
    sk_im_inds = np.zeros_like(sk_im, dtype=int)

    for i, p in enumerate(sk_pts):
        sk_im_inds[p[0], p[1]] = i

    kernel1 = np.uint8([[1, 1, 1],
                        [1, 0, 1],
                        [1, 1, 1]])
    edges = []
    for i, p in enumerate(sk_pts):
        mask = sk_im_inds[p[0] - 1:p[0] + 2, p[1] - 1:p[1] + 2]
        o = np.multiply(kernel1, mask)
        for c in o[o > 0]:
            edges.append(['{0}'.format(i), '{0}'.format(c)])
    # create graph
    G = defaultdict(list)
    for (ss, t) in edges:
        if t not in G[ss]:
            G[ss].append(t)
        if ss not in G[t]:
            G[t].append(ss)
    # print G.items()
    # find max path
    max_path = []
    for j in range(len(seed_inds)):
        all_paths = depth_first_search(G, str(int(seed_inds[j][0])))
        max_path2 = max(all_paths, key=lambda l: len(l))
        if len(max_path2) > len(max_path):
            max_path = max_path2
    # create new image only with max path
    sk_im_maxp = np.zeros_like(sk_im, dtype=int)
    for j in max_path:
        p = sk_pts[int(j)]
        sk_im_maxp[p[0], p[1]] = 1
    return sk_im_maxp


def skeleton_endpoints(skel):
    # make out input nice, possibly necessary
    skel = skel.copy()
    skel[skel != 0] = 1
    skel = np.uint8(skel)

    # apply the convolution
    kernel = np.uint8([[1, 1, 1],
                       [1, 10, 1],
                       [1, 1, 1]])
    src_depth = -1
    filtered = cv2.filter2D(skel, src_depth, kernel)

    # now look through to find the value of 11
    out = np.zeros_like(skel)
    out[np.where(filtered == 11)] = 1

    return out


def closest_node(node, nodes):
    closest_index = distance.cdist([node], nodes).argmin()
    return nodes[closest_index]


def detect_RV_points(_seg, septal_mv):
    rv_seg = np.squeeze(_seg == 3).astype(float)

    sk_pts = measure.find_contours(rv_seg, 0.8)
    if len(sk_pts) > 1:
        nb_pts = []
        for ll in range(len(sk_pts)):
            nb_pts.append(len(sk_pts[ll]))
        sk_pts = sk_pts[np.argmax(nb_pts)]
    sk_pts = np.squeeze(sk_pts)
    sk_pts = np.unique(sk_pts, axis=0)
    centroid = np.mean(sk_pts, axis=0)

    _lv_valve = closest_node(np.squeeze(septal_mv), sk_pts)
    ref = (_lv_valve - centroid) / norm(_lv_valve - centroid)

    sk_pts2 = sk_pts - centroid  # centre around centroid
    theta = np.zeros([len(sk_pts2), ])

    eps = 0.0001
    if len(sk_pts2) <= 5:
        print('Skeleton failed! Only of length {}'.format(len(sk_pts2)))
        _cl_pts = []
    else:
        # compute angle theta for skeleton points
        for k, ss in enumerate(sk_pts2):
            if (np.dot(ref, ss) / norm(ss) < 1.0 + eps) and (np.dot(ref, ss) / norm(ss) > 1.0 - eps):
                theta[k] = 0
            elif (np.dot(ref, ss) / norm(ss) < -1.0 + eps) and (np.dot(ref, ss) / norm(ss) > -1.0 - eps):
                theta[k] = 180
            else:
                theta[k] = math.acos(np.dot(ref, ss) / norm(ss)) * 180 / np.pi
            detp = ref[0] * ss[1] - ref[1] * ss[0]
            if detp > 0:
                theta[k] = 360 - theta[k]
        thinds = theta.argsort()
        sk_pts = sk_pts[thinds, :].astype(float)  # ordered centreline points

        # Remove duplicates
        sk_pts = binarymatrix(sk_pts)
        # fit b-spline curve to skeleton, sample fixed number of points
        tck, u = splprep(sk_pts.T, s=10.0, per=1, quiet=2)

        u_new = np.linspace(u.min(), u.max(), 80)
        _cl_pts = np.zeros([80, 2])
        _cl_pts[:, 0], _cl_pts[:, 1] = splev(u_new, tck)

    dist_rv = distance.cdist(_cl_pts, [_lv_valve])
    _ind_apex = dist_rv.argmax()
    _apex_RV = _cl_pts[_ind_apex, :]

    m = np.diff(_cl_pts[:, 0]) / np.diff(_cl_pts[:, 1])
    angle = np.arctan(m) * 180 / np.pi
    idx = np.sign(angle)
    _ind_free_wall = np.where(idx == -1)[0]

    _area = 10000 * np.ones(len(_ind_free_wall))
    for ai, ind in enumerate(_ind_free_wall):
        AB = np.linalg.norm(_lv_valve - _apex_RV)
        BC = np.linalg.norm(_lv_valve - _cl_pts[ind, :])
        AC = np.linalg.norm(_cl_pts[ind, :] - _apex_RV)
        if AC > 10 and BC > 10:
            _area[ai] = np.abs(AB ** 2 + BC ** 2 - AC ** 2)
    _free_rv_point = _cl_pts[_ind_free_wall[_area.argmin()], :]

    return np.asarray(_apex_RV), np.asarray(_lv_valve), np.asarray(_free_rv_point)


def remove_bad_junctions(skel):
    # make out input nice, possibly necessary
    skel = skel.copy()
    skel[skel != 0] = 1
    skel = np.uint8(skel)

    # kernel_A used for unnecessary nodes in L-shaped junctions (retain diags)
    kernels_A = [np.uint8([[0, 1, 0],
                           [1, 10, 1],
                           [0, 1, 0]])]
    src_depth = -1
    for k in kernels_A:
        filtered = cv2.filter2D(skel, src_depth, k)
        skel[filtered >= 13] = 0
        if len(np.where(filtered == 14)[0]) > 0:
            print('Warning! You have a 3x3 loop!')

    return skel


def depth_first_search(G, v, seen=None, path=None):
    if seen is None:
        seen = []
    if path is None:
        path = [v]

    seen.append(v)

    paths = []
    for t in G[v]:
        if t not in seen:
            t_path = path + [t]
            paths.append(tuple(t_path))
            paths.extend(depth_first_search(G, t, seen, t_path))
    return paths





#+============================ BRAM ADAPTED ==============================================


debug = False
Nsegments_length = 15


length_LV = []  # LA_2Ch and LA_4Ch
area_LV = []  # LA_2Ch and LA_4Ch
la_diams = []
length_perp = []
length_top = []
window_size, poly_order = 11, 3
QC_atria = 0
LV_atria_points_all = []
RV_atria_points_all = []
# MAPSE/TAPSE
LV_mid_mapse = []
LV_sept_mapse = []
LV_ant_mapse = []

subject_dir = '/Users/bramruijsink/Desktop/test_case/'
results_dir = '/Users/bramruijsink/Desktop/test_case/test_results/'
study_ID = 1

for s, seq in enumerate(['la_2Ch', 'la_4Ch']):
    filename_la_seg = os.path.join(subject_dir, '{}_seg_nnUnet.nii.gz'.format(seq))
    # print(filename_la_seg)
    if os.path.exists(filename_la_seg):
        nim = nib.load(filename_la_seg)
        la_seg = nim.get_fdata()
        dx, dy, dz = nim.header['pixdim'][1:4]
        area_per_voxel = dx * dy
        if len(la_seg.shape) == 4:
            la_seg = la_seg[:, :, 0, :]
        if seq == 'la_4Ch':
            la_seg = np.transpose(la_seg, [1, 0, 2])
        X, Y, N_frames = la_seg.shape
        # =============================================================================
        # Params
        # =============================================================================
        area_LV_aux = np.zeros(N_frames)
        length_LV_aux = np.zeros(N_frames)
        la_diams_aux = np.zeros((N_frames, Nsegments_length))  # LA_2Ch and LA_4Ch
        length_top_aux = np.zeros(N_frames)
        length_perp_aux = np.zeros(N_frames)
        LV_mid_mapse_seq = np.zeros(N_frames)
        LV_inferior_mapse_seq = np.zeros(N_frames)
        LV_anterior_mapse_seq = np.zeros(N_frames)
        RA_tapse_seq = np.zeros(N_frames)

        if seq == 'la_2Ch':
            points_LV_2Ch = np.zeros((N_frames, 4, 2))
            N_frames_2Ch = N_frames

        if seq == 'la_4Ch':
            N_frames_4Ch = N_frames
            points_LV_4Ch = np.zeros((N_frames, 4, 2))
            points_RV_4Ch = np.zeros((N_frames, 3, 2))

            # RA params
            la_diams_RV = np.zeros((N_frames, Nsegments_length))  # LA_4Ch
            length_top_RV = np.zeros(N_frames)  # LA_4Ch
            length_perp_RV = np.zeros(N_frames)  # LA_4Ch
            area_RV = np.zeros(N_frames)  # LA_4Ch

        # =============================================================================
        # Get largest connected components
        # =============================================================================
        for fr in range(N_frames):
            la_seg[:, :, fr] = getLargestCC(la_seg[:, :, fr])

        # =============================================================================
        # Compute area
        # =============================================================================
        for fr in range(N_frames):
            if seq == 'la_2Ch':
                area_LV_aux[fr] = np.sum(
                    np.squeeze(la_seg[:, :, fr] == 3).astype(float)) * area_per_voxel  # get atria label
            else:
                area_LV_aux[fr] = np.sum(
                    np.squeeze(la_seg[:, :, fr] == 4).astype(float)) * area_per_voxel  # get atria label
                area_RV[fr] = np.sum(np.squeeze(la_seg[:, :, fr] == 5).astype(float)) * area_per_voxel  # in mm2
        area_LV.append(area_LV_aux)
        # =============================================================================
        # Compute simpson's rule
        # =============================================================================
        for fr in range(N_frames):
            try:
                apex, mid_valve, anterior, inferior = detect_LV_points(la_seg[:, :, fr])
                points = np.vstack([apex, mid_valve, anterior, inferior])
                if seq == 'la_2Ch':
                    points_LV_2Ch[fr, :] = points
                if seq == 'la_4Ch':
                    apex_RV, rvlv_point, free_rv_point = detect_RV_points(la_seg[:, :, fr], anterior)
                    pointsRV = np.vstack([apex_RV, rvlv_point, free_rv_point])
                    points_LV_4Ch[fr, :] = points
                    points_RV_4Ch[fr, :] = pointsRV
            except Exception:
                logging.exception('Problem detecting LV or RV points {0} in {1} fr {2}'.format(study_ID, seq, fr))
                QC_atria = 1

            if QC_atria == 0:
                # =============================================================================
                # 2Ch
                # =============================================================================
                try:
                    la_dia, lentop, lenperp, points_non_roatate, contours_LA, lines_LV, points_LV = \
                        get_left_atrial_volumes(la_seg[:, :, fr], seq, fr, points,dx,dy)
                    la_diams_aux[fr, :] = la_dia
                    length_top_aux[fr] = lentop
                    length_perp_aux[fr] = lenperp

                    LV_mid_mapse_seq[fr] = lines_LV[0]  # length_apex_mid_valve
                    LV_inferior_mapse_seq[fr] = lines_LV[1]  # length_apex_inferior_2Ch
                    LV_anterior_mapse_seq[fr] = lines_LV[2]  # length_apex_anterior_2Ch
                    LV_atria_points_pf = np.zeros((9, 2))
                    LV_atria_points_pf[0, :] = points_non_roatate[0, :]  # final_mid_avalve
                    LV_atria_points_pf[1, :] = points_non_roatate[1, :]  # final_top_atria
                    LV_atria_points_pf[2, :] = points_non_roatate[2, :]  # final_perp_top_atria
                    LV_atria_points_pf[3, :] = points_non_roatate[3, :]  # final_atrial_edge1
                    LV_atria_points_pf[4, :] = points_non_roatate[4, :]  # final_atrial_edge2
                    LV_atria_points_pf[5, :] = points_LV[0, :]  # apex
                    LV_atria_points_pf[6, :] = points_LV[1, :]  # mid_valve
                    LV_atria_points_pf[7, :] = points_LV[2, :]  # inferior_2Ch/lateral_4Ch
                    LV_atria_points_pf[8, :] = points_LV[3, :]  # anterior_2Ch/septal_4Ch
                    LV_atria_points_all.append(LV_atria_points_pf)

                except Exception:
                    logging.exception('Problem in disk-making with subject {0} in {1} fr {2}'.
                                      format(study_ID, seq, fr))
                    QC_atria = 1
                # =============================================================================
                # 4Ch
                # =============================================================================
                if seq == 'la_4Ch':
                    try:
                        la_dia, lentop, lenperp, points_non_roatate, contours_RA, RA_tapse_seq[fr] = \
                            get_right_atrial_volumes(la_seg[:, :, fr], seq, fr, pointsRV, dx, dy)

                        la_diams_RV[fr, :] = la_dia
                        length_top_RV[fr] = lentop
                        length_perp_RV[fr] = lenperp

                        RV_atria_points_pf = np.zeros((8, 2))
                        RV_atria_points_pf[0, :] = points_non_roatate[0, :]  # final_mid_avalve
                        RV_atria_points_pf[1, :] = points_non_roatate[1, :]  # final_top_atria
                        RV_atria_points_pf[2, :] = points_non_roatate[2, :]  # final_perp_top_atria
                        RV_atria_points_pf[3, :] = points_non_roatate[3, :]  # final_atrial_edge1
                        RV_atria_points_pf[4, :] = points_non_roatate[4, :]  # final_atrial_edge2
                        RV_atria_points_pf[5, :] = pointsRV[0, :]  # apex_RV
                        RV_atria_points_pf[6, :] = pointsRV[1, :]  # rvlv_point
                        RV_atria_points_pf[7, :] = pointsRV[2, :]  # free_rv_point
                        RV_atria_points_all.append(RV_atria_points_pf)
                    except Exception:
                        logging.exception(
                            'RV Problem in disk-making with subject {0} in {1} fr {2}'.format(study_ID, seq, fr))
                        QC_atria = 1

        # =============================================================================
        # MAPSE/TAPSE
        # =============================================================================
        LV_mid_mapse.append(LV_mid_mapse_seq[0] - LV_mid_mapse_seq)
        LV_sept_mapse.append(LV_inferior_mapse_seq[0] - LV_inferior_mapse_seq)  # inferior_2Ch/septal_4Ch
        LV_ant_mapse.append(LV_anterior_mapse_seq[0] - LV_anterior_mapse_seq)  # anterior_2Ch/lateral_4Ch
        if seq == 'la_4Ch':
            RA_tapse = RA_tapse_seq[0] - RA_tapse_seq
            RV_atria_points_all = np.squeeze(np.asarray(RV_atria_points_all))
        length_LV.append(length_LV_aux)
        la_diams.append(la_diams_aux)
        length_top.append(length_top_aux)
        length_perp.append(length_perp_aux)

    else:
        QC_atria = 1

if QC_atria == 0:
    N_frames = max(N_frames_2Ch,N_frames_4Ch)
    if N_frames_2Ch == N_frames_4Ch:
        area_LV = np.array(area_LV).T
        LV_mid_mapse = np.array(LV_mid_mapse).T
        LV_sept_mapse = np.array(LV_sept_mapse).T
        LV_ant_mapse = np.array(LV_ant_mapse).T
        la_diams = np.array(la_diams)
        la_diams = np.transpose(la_diams, (1, 2, 0))
        length_top = np.array(length_top).T

    # =============================================================================
    # Save points
    # =============================================================================
    LV_atria_points_all = np.squeeze(np.asarray(LV_atria_points_all))
    np.save(os.path.join(results_dir, '{}_{}_LV_points.py'.format(study_ID, seq)), LV_atria_points_all)
    RV_atria_points_all = np.squeeze(np.asarray(RV_atria_points_all))
    np.save(os.path.join(results_dir, '{}_{}_RV_points.py'.format(study_ID, seq)), RV_atria_points_all)

    points_LV_2Ch = np.squeeze(np.asarray(points_LV_2Ch))
    np.save(os.path.join(results_dir, 'points_LV_2Ch.npy'), points_LV_2Ch)
    points_LV_4Ch = np.squeeze(np.asarray(points_LV_4Ch))
    np.save(os.path.join(results_dir, 'points_LV_4Ch.npy'), points_LV_4Ch)
    points_RV_4Ch = np.squeeze(np.asarray(points_RV_4Ch))
    np.save(os.path.join(results_dir, 'points_RV_4Ch.npy'), points_RV_4Ch)

    # =============================================================================
    # Compute volumes
    # =============================================================================
    LA_volumes_SR = np.zeros(N_frames)
    LA_volumes_2Ch = np.zeros(N_frames_2Ch)
    LA_volumes_4Ch = np.zeros(N_frames_4Ch)
    RA_volumes_area = np.zeros(N_frames_4Ch)
    LA_volumes_area = np.zeros(N_frames)
    for fr in range(max([N_frames_4Ch, N_frames_2Ch])):
        # Simpson's rule
        if N_frames_2Ch == N_frames_4Ch:
            d1d2 = la_diams[fr, :, 0] * la_diams[fr, :, 1]
            length = np.min([length_top[fr, 0], length_top[fr, 1]])
            LA_volumes_SR[fr] = math.pi / 4 * length * np.sum(d1d2) / Nsegments_length / 1000


        # la 2Ch
        if N_frames_2Ch == N_frames_4Ch:
            d1d2 = la_diams[fr, :, 0] * la_diams[fr, :, 0]
            length = np.min([length_top[fr, 0], length_top[fr, 0]])
            LA_volumes_2Ch[fr] = math.pi / 4 * length * np.sum(d1d2) / Nsegments_length / 1000
        else:
            if fr < N_frames_2Ch:
                d1d2 = la_diams[0][fr, :] * la_diams[0][fr, :]
                length = np.min([length_top[0][fr], length_top[0][fr]])
                LA_volumes_2Ch[fr] = math.pi / 4 * length * np.sum(d1d2) / Nsegments_length / 1000

        if N_frames_2Ch == N_frames_4Ch:
            # la 4Ch
            d1d2 = la_diams[fr, :, 1] * la_diams[fr, :, 1]
            length = np.min([length_top[fr, 1], length_top[fr, 1]])
            LA_volumes_4Ch[fr] = math.pi / 4 * length * np.sum(d1d2) / Nsegments_length / 1000
        else:
            if fr < N_frames_4Ch:
                d1d2 = la_diams[1][fr, :] * la_diams[1][fr, :]
                length = np.min([length_top[1][fr], length_top[1][fr]])
                LA_volumes_4Ch[fr] = math.pi / 4 * length * np.sum(d1d2) / Nsegments_length / 1000

        # Area
        if N_frames_2Ch == N_frames_4Ch:
            LA_volumes_area[fr] = 0.85 * area_LV[fr, 0] * area_LV[fr, 1] / length / 1000


    x = np.linspace(0, N_frames_2Ch - 1, N_frames_2Ch)
    xx = np.linspace(np.min(x), np.max(x), N_frames_2Ch)
    itp = interp1d(x, LA_volumes_2Ch)
    yy_sg = savgol_filter(itp(xx), window_size, poly_order)
    LA_volumes_2Ch_smooth = yy_sg

    x = np.linspace(0, N_frames_4Ch - 1, N_frames_4Ch)
    xx = np.linspace(np.min(x), np.max(x), N_frames_4Ch)
    itp = interp1d(x, LA_volumes_4Ch)
    yy_sg = savgol_filter(itp(xx), window_size, poly_order)
    LA_volumes_4Ch_smooth = yy_sg


    np.savetxt(os.path.join(results_dir, 'LA_volumes_2Ch.txt'), LA_volumes_2Ch)
    np.savetxt(os.path.join(results_dir, 'LA_volumes_4Ch.txt'), LA_volumes_4Ch)
    np.savetxt(os.path.join(results_dir, 'LA_volumes_SR.txt'), LA_volumes_SR)
    np.savetxt(os.path.join(results_dir, 'LA_volumes_area.txt'), LA_volumes_area)
    np.savetxt(os.path.join(results_dir, 'LA_volumes_2Ch_smooth.txt'), LA_volumes_2Ch_smooth)
    np.savetxt(os.path.join(results_dir, 'LA_volumes_4Ch_smooth.txt'), LA_volumes_4Ch_smooth)

    if N_frames_2Ch == N_frames_4Ch:
        x = np.linspace(0, N_frames - 1, N_frames)
        xx = np.linspace(np.min(x), np.max(x), N_frames)
        itp = interp1d(x, LA_volumes_SR)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volumes_SR_smooth = yy_sg

        itp = interp1d(x, LA_volumes_area)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volumes_area_smooth = yy_sg

        np.savetxt(os.path.join(results_dir, 'LA_volumes_SR_smooth.txt'), LA_volumes_SR_smooth)
        np.savetxt(os.path.join(results_dir, 'LA_volumes_area_smooth.txt'), LA_volumes_area_smooth)

    # Simpson and Area method if not the same number of slices between methods
    else:
        max_frames = max(N_frames_2Ch, N_frames_4Ch)
        ref_x = np.linspace(0, max_frames - 1, max_frames)
        diams_2Ch = np.zeros_like(length_top[0])
        diams_4Ch = np.zeros_like(length_top[1])

        for fr in range(N_frames_2Ch):
            diams_2Ch[fr] = np.average(la_diams[0][fr])
        for fr in range(N_frames_4Ch):
            diams_4Ch[fr] = np.average(la_diams[1][fr])
        diams_all = [diams_2Ch, diams_4Ch]
        # interpolate the shortest to the longest sequence
        if N_frames_2Ch == max_frames:
            colmn = 1
            colmn2 = 0
        else:
            colmn = 0
            colmn2= 1

        arr2_interp = interp1d(np.arange(area_LV[colmn].size), area_LV[colmn])
        LA_area_Ch_stretch = arr2_interp(np.linspace(0, area_LV[colmn].size - 1, ref_x.size))
        len_arr2_interp = interp1d(np.arange(length_top[colmn].size), length_top[colmn])
        LA_length_Ch_stretch = len_arr2_interp(np.linspace(0, length_top[colmn].size - 1, ref_x.size))
        diams_arr2_interp = interp1d(np.arange(diams_all[colmn].size), diams_all[colmn])
        LA_diams_Ch_stretch = diams_arr2_interp(np.linspace(0, diams_all[colmn].size - 1, ref_x.size))
        # calculate simpson and area
        for fr in range(max_frames):
            length = np.min([length_top[colmn2][fr], LA_length_Ch_stretch[fr]])
            LA_volumes_area[fr] = 0.85 * area_LV[colmn2][fr] * LA_area_Ch_stretch[fr] / length / 1000

            d1d2 = diams_all[colmn2][fr] * LA_diams_Ch_stretch[fr]
            length = np.min([length_top[colmn2][fr], LA_length_Ch_stretch[fr]])
            #LA_volumes_SR[fr] = math.pi / 4 * (length * d1d2) / 1000
            LA_volumes_SR[fr] = math.pi / 4 * length * d1d2 / 1000


        xx = np.linspace(np.min(ref_x), np.max(ref_x), max_frames)
        itp = interp1d(ref_x, LA_volumes_area)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volumes_area_smooth = yy_sg
        itp = interp1d(ref_x, LA_volumes_SR)
        yy_sg = savgol_filter(itp(xx), window_size, poly_order)
        LA_volumes_SR_smooth = yy_sg
        np.savetxt(os.path.join(results_dir, 'LA_volumes_SR_smooth.txt'), LA_volumes_SR_smooth)
        np.savetxt(os.path.join(results_dir, 'LA_volumes_area_smooth.txt'), LA_volumes_area_smooth)

    # RA volumes
    RA_volumes_SR = np.zeros(N_frames_4Ch)
    for fr in range(N_frames_4Ch):
        d1d2 = la_diams_RV[fr, :] * la_diams_RV[fr, :]
        length = length_top_RV[fr]

        RA_volumes_SR[fr] = math.pi / 4 * length * np.sum(d1d2) / Nsegments_length / 1000
        RA_volumes_area[fr] = 0.85 * area_RV[fr] * area_RV[fr] / length / 1000

    x = np.linspace(0, N_frames_4Ch - 1, N_frames_4Ch)
    xx = np.linspace(np.min(x), np.max(x), N_frames_4Ch)
    itp = interp1d(x, RA_volumes_SR)
    yy_sg = savgol_filter(itp(xx), window_size, poly_order)
    RA_volumes_SR_smooth = yy_sg
    itp = interp1d(x, RA_volumes_area)
    yy_sg = savgol_filter(itp(xx), window_size, poly_order)
    RA_volumes_area_smooth = yy_sg

    np.savetxt(os.path.join(results_dir, 'RA_volumes_SR.txt'), RA_volumes_SR)
    np.savetxt(os.path.join(results_dir, 'RA_volumes_area.txt'), RA_volumes_area)
    np.savetxt(os.path.join(results_dir, 'RA_volumes_SR_smooth.txt'), RA_volumes_SR_smooth)
    np.savetxt(os.path.join(results_dir, 'RA_volumes_area_smooth.txt'), RA_volumes_area_smooth)

    # =============================================================================
    # PLOTS
    # =============================================================================
    plt.figure()
    plt.plot(LA_volumes_2Ch_smooth, label='LA volumes 2Ch')
    plt.plot(LA_volumes_4Ch_smooth, label='LA volumes 4Ch')
    #if N_frames_2Ch == N_frames_4Ch:
    plt.plot(LA_volumes_SR_smooth, label='Simpson method')
    plt.plot(LA_volumes_area_smooth, label='Area method')
    plt.legend()
    plt.title('Left Atrial Volume')
    plt.savefig(os.path.join(results_dir, 'LA_volume_area.png'))
    plt.close('all')

    plt.figure()
    plt.plot(RA_volumes_SR_smooth, label='Simpson method')
    plt.plot(RA_volumes_area_smooth, label='Area method')
    plt.legend()
    plt.title('Right Atrial Volume')
    plt.savefig(os.path.join(results_dir, 'RA_volume_area.png'))
    plt.close('all')

    # =============================================================================
    # Compute condsuit and reservoir
    # =============================================================================
    #if N_frames_2Ch == N_frames_4Ch:
    try:
        LAmax = np.max(LA_volumes_SR_smooth)
        ES_frame_LA = LA_volumes_SR_smooth.argmax()
        LAmin = np.min(LA_volumes_SR_smooth)
        vol_first_deriv = np.gradient(LA_volumes_SR_smooth[::2])
        indx_local_max = argrelextrema(vol_first_deriv, np.greater)
        if len(indx_local_max[0]) > 1:
            indx_local_max = np.squeeze(np.asarray(indx_local_max))
        elif len(indx_local_max[0]) == 1:
            indx_local_max = indx_local_max[0]

        indx_local_max = np.squeeze(np.asarray(indx_local_max[indx_local_max > int(ES_frame_LA / 2)])) * 2
        if indx_local_max.size > 0:
            LA_reservoir = np.mean(LAmax - LA_volumes_SR_smooth[indx_local_max])
            LA_reservoir_point = int(np.mean(indx_local_max))
            LA_pump_point = np.argmin(LA_volumes_SR_smooth[LA_reservoir_point:]) + LA_reservoir_point
            LA_pump = LA_volumes_SR_smooth[LA_reservoir_point] - LA_volumes_SR_smooth[LA_pump_point]

            fig, ax = plt.subplots()
            ax.plot(LA_volumes_SR_smooth)
            ax.plot(LA_reservoir_point, LA_volumes_SR_smooth[LA_reservoir_point], 'ro')
            ax.annotate('LA_reservoir', (LA_reservoir_point, LA_volumes_SR_smooth[LA_reservoir_point]))
            ax.plot(ES_frame_LA, LAmax, 'ro')
            ax.annotate('LA max', (ES_frame_LA, LAmax))
            ax.plot(LA_pump_point, LA_volumes_SR_smooth[LA_pump_point], 'ro')
            ax.annotate('LA pump', (LA_pump_point, LA_volumes_SR_smooth[LA_pump_point]))
            ax.set_title('{}: LAV'.format(study_ID))
            plt.savefig(os.path.join(results_dir, 'LA_volume_points.png'))
            plt.close('all')
        else:
            QC_atria = 1
    except Exception:
        logging.exception('Problem in calculating LA conduit a with subject {0}'.format(study_ID))
        QC_atria = 1


    # =============================================================================
    # Compute conduit and reservoir RV
    # =============================================================================
    try:
        RAmax = np.max(RA_volumes_SR_smooth)
        ES_frame = RA_volumes_SR_smooth.argmax()
        RAmin = np.min(RA_volumes_SR_smooth)
        vol_first_deriv = np.gradient(RA_volumes_SR_smooth[::2])
        indx_local_max = argrelextrema(vol_first_deriv, np.greater)
        if len(indx_local_max[0]) > 1:
            indx_local_max = np.squeeze(np.asarray(indx_local_max))
        elif len(indx_local_max[0]) == 1:
            indx_local_max = indx_local_max[0]

        indx_local_max = np.squeeze(np.asarray(indx_local_max[indx_local_max > int(ES_frame / 2)])) * 2
        if indx_local_max.size > 0:
            RA_reservoir = np.mean(RAmax - RA_volumes_SR_smooth[indx_local_max])
            RA_reservoir_point = int(np.mean(indx_local_max))
            RA_pump_point = np.argmin(RA_volumes_SR_smooth[RA_reservoir_point:]) + RA_reservoir_point

            RA_pump = RA_volumes_SR_smooth[RA_reservoir_point] - RA_volumes_SR_smooth[RA_pump_point]

            fig, ax = plt.subplots()
            ax.plot(RA_volumes_SR_smooth)
            ax.plot(RA_reservoir_point, RA_volumes_SR_smooth[RA_reservoir_point], 'ro')
            ax.annotate('RA_reservoir', (RA_reservoir_point, RA_volumes_SR_smooth[RA_reservoir_point]))
            ax.plot(ES_frame, RAmax, 'ro')
            ax.annotate('RA max', (ES_frame, RAmax))
            ax.plot(RA_pump_point, RA_volumes_SR_smooth[RA_pump_point], 'ro')
            ax.annotate('RA pump', (RA_pump_point, RA_volumes_SR_smooth[RA_pump_point]))
            ax.set_title('{}: RAV'.format(study_ID))
            plt.savefig(os.path.join(results_dir, 'RA_volume_points.png'))
            plt.close('all')
        else:
            QC_atria = 1
    except Exception:
        logging.exception('Problem in calculating RA conduit a with subject {0}'.format(study_ID))
        QC_atria = 1

    # =============================================================================
    # MAPSE
    # =============================================================================
    try:
        if N_frames_2Ch == N_frames_4Ch:
            f, ax = plt.subplots()
            f2, ax2 = plt.subplots()

            LV_sept_mapse_smooth = np.zeros_like(LV_sept_mapse)
            LV_ant_mapse_smooth = np.zeros_like(LV_ant_mapse)
            LV_mid_mapse_smooth = np.zeros_like(LV_mid_mapse)


            for s, seq in enumerate(['la_2Ch', 'la_4Ch']):
                No_frames = len(LV_sept_mapse[:, s])
                x = np.linspace(0, No_frames - 1, No_frames)
                xx = np.linspace(np.min(x), np.max(x), No_frames)
                itp = interp1d(x, LV_sept_mapse[:, s])
                LV_sept_mapse_smooth[:, s] = savgol_filter(itp(xx), window_size, poly_order)

                itp = interp1d(x, LV_ant_mapse[:, s])
                LV_ant_mapse_smooth[:, s] = savgol_filter(itp(xx), window_size, poly_order)

                itp = interp1d(x, LV_mid_mapse[:, s])
                LV_mid_mapse_smooth[:, s] = savgol_filter(itp(xx), window_size, poly_order)
                np.savetxt('{0}/LV_sept_mapse_{1}.txt'.format(results_dir, seq), LV_sept_mapse[:, s])
                np.savetxt('{0}/LV_ant_mapse_{1}.txt'.format(results_dir, seq), LV_ant_mapse[:, s])
                np.savetxt('{0}/LV_mid_mapse_{1}.txt'.format(results_dir, seq), LV_mid_mapse[:, s])

                np.savetxt('{0}/LV_sept_mapse_smooth_{1}.txt'.format(results_dir, seq), LV_sept_mapse_smooth[:, s])
                np.savetxt('{0}/LV_ant_mapse_smooth_{1}.txt'.format(results_dir, seq), LV_ant_mapse_smooth[:, s])
                np.savetxt('{0}/LV_mid_mapse_smooth_{1}.txt'.format(results_dir, seq), LV_mid_mapse_smooth[:, s])

                ax.plot(LV_sept_mapse[:, s], label='Septal {0} MAPSE'.format(seq))
                ax.plot(LV_ant_mapse[:, s], label='Ant {0} MAPSE'.format(seq))
                ax.plot(LV_mid_mapse[:, s], label='Mid {0} MAPSE'.format(seq))

                ax2.plot(LV_sept_mapse_smooth[:, s], label='Septal {0} MAPSE'.format(seq))
                ax2.plot(LV_ant_mapse_smooth[:, s], label='Ant {0} MAPSE'.format(seq))
                ax2.plot(LV_mid_mapse_smooth[:, s], label='Mid {0} MAPSE'.format(seq))

            ax.legend()
            ax.set_title('MAPSE')
            f.savefig(os.path.join(results_dir, 'MAPSE.png'))

            ax2.legend()
            ax2.set_title('MAPSE smooth')
            f2.savefig(os.path.join(results_dir, 'MAPSE_smooth.png'))
            plt.close('all')

            itp = interp1d(x, RA_tapse)
            RA_tapse_smooth = savgol_filter(itp(xx), window_size, poly_order)
            np.savetxt('{0}/RA_tapse_smooth_la4Ch.txt'.format(results_dir), RA_tapse_smooth)
            np.savetxt('{0}/RA_tapse_la4Ch.txt'.format(results_dir), RA_tapse)

            f, ax = plt.subplots()
            ax.plot(RA_tapse_smooth)
            ax.set_title('TAPSE_smooth.png')
            f.savefig(os.path.join(results_dir, 'TAPSE.png'))
            plt.close('all')

            f, ax = plt.subplots()
            ax.plot(RA_tapse_smooth)
            ax.set_title('{}: TAPSE'.format(study_ID))
            ax.plot(RA_tapse_smooth.argmax(), RA_tapse_smooth[RA_tapse_smooth.argmax()], 'ro')
            ax.annotate('TAPSE', (RA_tapse_smooth.argmax(), RA_tapse_smooth[RA_tapse_smooth.argmax()]))
            f.savefig(os.path.join(results_dir, 'TAPSE_final.png'))
            plt.close('all')

            f, ax = plt.subplots()
            ax.plot(LV_mid_mapse_smooth[:, 0])
            ax.plot(LV_mid_mapse_smooth[:, 0].argmax(), LV_mid_mapse_smooth[:, 0][LV_mid_mapse_smooth[:, 0].argmax()], 'ro')
            ax.annotate('MAPSE', (LV_mid_mapse_smooth[:, 0].argmax(), LV_mid_mapse_smooth[:, 0][LV_mid_mapse_smooth[:, 0].argmax()]))
            ax.set_title('{}: MAPSE'.format(study_ID))
            f.savefig(os.path.join(results_dir, 'MAPSE_final.png'))
            plt.close('all')


        else:
            f, ax = plt.subplots()
            f2, ax2 = plt.subplots()

            LV_sept_mapse_smooth = []
            LV_ant_mapse_smooth = []
            LV_mid_mapse_smooth = []

            for s, seq in enumerate(['la_2Ch', 'la_4Ch']):
                if seq == 'la_2Ch':
                    x = np.linspace(0, N_frames_2Ch - 1, N_frames_2Ch)
                    xx = np.linspace(np.min(x), np.max(x), N_frames_2Ch)
                else:
                    x = np.linspace(0, N_frames_4Ch - 1, N_frames_4Ch)
                    xx = np.linspace(np.min(x), np.max(x), N_frames_4Ch)

                itp = interp1d(x, LV_sept_mapse[s])
                LV_sept_mapse_smooth.append(savgol_filter(itp(xx), window_size, poly_order))
                itp = interp1d(x, LV_ant_mapse[s])
                LV_ant_mapse_smooth.append(savgol_filter(itp(xx), window_size, poly_order))
                itp = interp1d(x, LV_mid_mapse[s])
                LV_mid_mapse_smooth.append(savgol_filter(itp(xx), window_size, poly_order))

                np.savetxt('{0}/LV_sept_mapse_{1}.txt'.format(results_dir, seq), LV_sept_mapse[s])
                np.savetxt('{0}/LV_ant_mapse_{1}.txt'.format(results_dir, seq), LV_ant_mapse[s])
                np.savetxt('{0}/LV_mid_mapse_{1}.txt'.format(results_dir, seq), LV_mid_mapse[s])

                np.savetxt('{0}/LV_sept_mapse_smooth_{1}.txt'.format(results_dir, seq), LV_sept_mapse_smooth[s])
                np.savetxt('{0}/LV_ant_mapse_smooth_{1}.txt'.format(results_dir, seq), LV_ant_mapse_smooth[s])
                np.savetxt('{0}/LV_mid_mapse_smooth_{1}.txt'.format(results_dir, seq), LV_mid_mapse_smooth[s])

                ax.plot(LV_sept_mapse[s], label='Septal {0} MAPSE'.format(seq))
                ax.plot(LV_ant_mapse[s], label='Ant {0} MAPSE'.format(seq))
                ax.plot(LV_mid_mapse[s], label='Mid {0} MAPSE'.format(seq))

                ax2.plot(LV_sept_mapse_smooth[s], label='Septal {0} MAPSE'.format(seq))
                ax2.plot(LV_ant_mapse_smooth[s], label='Ant {0} MAPSE'.format(seq))
                ax2.plot(LV_mid_mapse_smooth[s], label='Mid {0} MAPSE'.format(seq))

            ax.legend()
            ax.set_title('MAPSE')
            f.savefig(os.path.join(results_dir, 'MAPSE.png'))

            ax2.legend()
            ax2.set_title('MAPSE smooth')
            f2.savefig(os.path.join(results_dir, 'MAPSE_smooth.png'))
            f2.savefig(os.path.join(results_dir, 'MAPSE_final.png'))
            plt.close('all')

            x = np.linspace(0, N_frames_4Ch - 1, N_frames_4Ch)
            xx = np.linspace(np.min(x), np.max(x), N_frames_4Ch)
            itp = interp1d(x, RA_tapse)
            RA_tapse_smooth = savgol_filter(itp(xx), window_size, poly_order)
            np.savetxt('{0}/RA_tapse_smooth_la4Ch.txt'.format(results_dir), RA_tapse_smooth)
            np.savetxt('{0}/RA_tapse_la4Ch.txt'.format(results_dir), RA_tapse)

            f, ax = plt.subplots()
            ax.plot(RA_tapse_smooth)
            #ax.plot(RA_tapse)
            ax.set_title('TAPSE')
            f.savefig(os.path.join(results_dir, 'TAPSE.png'))
            plt.close('all')

            f, ax = plt.subplots()
            ax.plot(RA_tapse_smooth)
            ax.set_title('{}: TAPSE'.format(study_ID))
            ax.plot(RA_tapse_smooth.argmax(), RA_tapse_smooth[RA_tapse_smooth.argmax()], 'ro')
            ax.annotate('TAPSE', (RA_tapse_smooth.argmax(), RA_tapse_smooth[RA_tapse_smooth.argmax()]))
            f.savefig(os.path.join(results_dir, 'TAPSE_final.png'))
            plt.close('all')

    except Exception:
        logging.exception('Problem in calculating MAPSE/TAPSE with subject {0}'.format(study_ID))
        QC_atria = 1

    # =============================================================================
    # SAVE RESULTS
    # =============================================================================
    vols = np.zeros(39, dtype=object)
    vols[0] = study_ID
    if QC_atria == 0:
        #if N_frames_2Ch == N_frames_4Ch:
        vols[1] = LAmin  # LA min simpsons
        vols[2] = LAmax  # LA max simpsons
        vols[3] = np.min(LA_volumes_area_smooth)  # LA min area
        vols[4] = np.max(LA_volumes_area_smooth)  # LA max area
        vols[9] = LA_reservoir  # LA reservoir
        vols[10] = LA_pump  # LA pump
        vols[11] = LA_volumes_SR_smooth.argmin()  # LA reservoir
        vols[12] = LA_volumes_SR_smooth.argmax()  # LA pump
        vols[13] = LA_reservoir_point  # LA reservoir
        vols[14] = LA_pump_point  # LA pump

        vols[5] = np.min(LA_volumes_2Ch_smooth)  # LA min 2Ch
        vols[6] = np.max(LA_volumes_2Ch_smooth)  # LA max 2Ch
        vols[7] = np.min(LA_volumes_4Ch_smooth)  # LA min 4Ch
        vols[8] = np.max(LA_volumes_4Ch_smooth)  # LA max 4Ch

        vols[15] = RAmin  # RA min simpsons
        vols[16] = RAmax  # RA max simpsons
        vols[17] = np.min(RA_volumes_area_smooth)  # RA min area
        vols[18] = np.max(RA_volumes_area_smooth)  # RA max area
        vols[19] = RA_reservoir  # RA reservoir
        vols[20] = RA_pump  # RA pump

        vols[21] = RA_volumes_SR_smooth.argmin()  # LA reservoir
        vols[22] = RA_volumes_SR_smooth.argmax()  # LA pump
        vols[23] = RA_reservoir_point  # LA reservoir
        vols[24] = RA_pump_point  # LA pump

        if N_frames_2Ch == N_frames_4Ch:
            vols[25] = LV_sept_mapse[0, 0]  # LV 2Ch EDV sept_mapse
            vols[26] = np.max(LV_sept_mapse_smooth[:, 0])  # LV 2Ch ESV sept_mapse
            vols[27] = LV_mid_mapse[0, 0]  # LV 2Ch EDV mid_mapse
            vols[28] = np.max(LV_mid_mapse_smooth[:, 0])  # LV 2Ch ESV mid_mapse
            vols[29] = LV_ant_mapse[0, 0]  # LV 2Ch EDV ant_mapse
            vols[30] = np.max(LV_ant_mapse_smooth[:, 0])  # LV 2Ch ESV ant_mapse

            vols[31] = LV_sept_mapse[0, 1]  # LV 4Ch EDV sept_mapse
            vols[32] = np.max(LV_sept_mapse_smooth[:, 1])  # LV 4Ch ESV sept_mapse
            vols[33] = LV_mid_mapse[0, 1]  # LV 4Ch EDV mid_mapse
            vols[34] = np.max(LV_mid_mapse_smooth[:, 1])  # LV 4Ch ESV mid_mapse
            vols[35] = LV_ant_mapse[0, 1]  # LV 4Ch EDV ant_mapse
            vols[36] = np.max(LV_ant_mapse_smooth[:, 1])  # LV 4Ch ESV ant_mapse
        else:
            vols[25] = LV_sept_mapse[0][0]  # LV 2Ch EDV sept_mapse
            vols[26] = np.max(LV_sept_mapse_smooth[0])  # LV 2Ch ESV sept_mapse
            vols[27] = LV_mid_mapse[0][0]  # LV 2Ch EDV mid_mapse
            vols[28] = np.max(LV_mid_mapse_smooth[0])  # LV 2Ch ESV mid_mapse
            vols[29] = LV_ant_mapse[0][0]  # LV 2Ch EDV ant_mapse
            vols[30] = np.max(LV_ant_mapse_smooth[0])  # LV 2Ch ESV ant_mapse

            vols[31] = LV_sept_mapse[1][0]  # LV 4Ch EDV sept_mapse
            vols[32] = np.max(LV_sept_mapse_smooth[1])  # LV 4Ch ESV sept_mapse
            vols[33] = LV_mid_mapse[1][0]  # LV 4Ch EDV mid_mapse
            vols[34] = np.max(LV_mid_mapse_smooth[1])  # LV 4Ch ESV mid_mapse
            vols[35] = LV_ant_mapse[1][0]  # LV 4Ch EDV ant_mapse
            vols[36] = np.max(LV_ant_mapse_smooth[1])  # LV 4Ch ESV ant_mapse
        vols[37] = RA_tapse[0]  # RA 4Ch EDV ant_mapse
        vols[38] = np.max(RA_tapse_smooth)  # RA 4Ch ESV ant_mapse

    vols = np.reshape(vols, [1, 39])
    df = pd.DataFrame(vols)
    df.to_csv('{0}/clinical_measure_atria.csv'.format(results_dir),
              header=['eid', 'LAEDVsimp', 'LAESVsimp', 'LAEDVarea', 'LAESVarea', 'LAEDV 2Ch', 'LAESV 2Ch',
                      'LAEDV 4Ch', 'LAESV 4Ch', 'LARes', 'LAPump', 'point min LA', 'point max LA',
                      'point reservoir LA', 'point pump LA', 'RAEDVsimp',
                      'RAESVsimp', 'RAEDVarea', 'RAESVarea', 'RARes', 'RAPump', 'point min RA', 'point max RA',
                      'point reservoir RA', 'point pump RA',
                      'LA_EDVsept_mapse2Ch', 'LA_ESVsept_mapse2Ch',
                      'LA_EDVmid_mapse2Ch', 'LA_ESVmid_mapse2Ch', 'LA_EDVant_mapse2Ch', 'LA_ESVant_mapse2Ch',
                      'LA_EDVsept_mapse4Ch', 'LA_ESVsept_mapse4Ch', 'LA_EDVmid_mapse4Ch',
                      'LA_ESVmid_mapse4Ch',
                      'LA_EDVant_mapse4Ch', 'LA_ESVant_mapse4Ch', 'RA_EDV_tapse4Ch',
                      'RA_ESV_tapse4Ch'], index=False)


#======= BRAM TO RUN DATA


