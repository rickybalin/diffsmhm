import numpy as np
import matplotlib.pyplot as plt

try:
    from mpi4py import MPI

    COMM = MPI.COMM_WORLD
    RANK = COMM.Get_rank()
    N_RANKS = COMM.Get_size()
except ImportError:
    COMM = None
    RANK = 0
    N_RANKS = 1

from diffsmhm.galhalo_models.sigmoid_smhm import (
    DEFAULT_PARAM_VALUES as smhm_params
)
from diffsmhm.galhalo_models.sigmoid_smhm_sigma import (
    DEFAULT_PARAM_VALUES as smhm_sigma_params
)
from diffsmhm.galhalo_models.sigmoid_disruption import (
    DEFAULT_PARAM_VALUES as disruption_params
)
from diffsmhm.galhalo_models.sigmoid_quenching import (
    DEFAULT_PARAM_VALUES as quenching_params
)

from diffsmhm.loader import load_and_chop_data_bolshoi_planck

from diffsmhm.galhalo_models.merging import _calculate_indx_to_deposit

from diff_sm import compute_weight_and_jac_quench

from rpwp import compute_rpwp

from adam import adam
from error import mse_rpwp_quench_adam_wrapper

# data files and params
halo_file="/home/jwick/data/value_added_orphan_complete_bpl_1.002310.h5"
particle_file="/home/jwick/data/hlist_1.00231.particles.halotools_v0p4.hdf5"
box_length = 250.0 # Mpc
buff_wprp = 20.0 # Mpc

mass_bin_edges = np.array([10.6, 10.7], dtype=np.float64)

rpbins = np.logspace(-1, 1.5, 13, dtype=np.float64)
zmax = 20.0 # Mpc

theta = np.array(list(smhm_params.values()) +
                 list(smhm_sigma_params.values()) +
                 list(disruption_params.values()) +
                 list(quenching_params.values()), dtype=np.float64)

n_params = len(theta)
n_rpbins = len(rpbins) - 1

# 1) load data
halos, _ = load_and_chop_data_bolshoi_planck(
                    particle_file,
                    halo_file,
                    box_length,
                    buff_wprp,
                    host_mpeak_cut=14.7)

idx_to_deposit = _calculate_indx_to_deposit(halos["upid"], halos["halo_id"])

print(RANK, len(halos["halo_id"]), flush=True)

# 2) obtain "goal" measurement
parameter_perturbations = np.random.uniform(low=0.95, high=1.05, size=n_params)

theta_goal = theta * parameter_perturbations

# rpwp, quenched and unquenched
w_q, dw_q, w_nq, dw_nq = compute_weight_and_jac_quench(
                        halos["logmpeak"],
                        halos["loghost_mpeak"],
                        halos["vmax_frac"],
                        halos["upid"],
                        halos["time_since_infall"],
                        idx_to_deposit,
                        mass_bin_edges[0], mass_bin_edges[1],
                        theta
)

wgt_mask_quench = w_q > 0
wgt_mask_no_quench = w_nq > 0

if RANK == 0:
    print("goal weights done", flush=True)

# goal rpwp computation
rpwp_q_goal, gq = compute_rpwp(
                        x1=halos["halo_x"][wgt_mask_quench],
                        y1=halos["halo_y"][wgt_mask_quench],
                        z1=halos["halo_z"][wgt_mask_quench],
                        w1=w_q[wgt_mask_quench],
                        w1_jac=dw_q[:, wgt_mask_quench],
                        inside_subvol=halos["_inside_subvol"][wgt_mask_quench],
                        rpbins=rpbins,
                        zmax=zmax,
                        boxsize=box_length
)

rpwp_nq_goal, gnq = compute_rpwp(
                        x1=halos["halo_x"][wgt_mask_no_quench],
                        y1=halos["halo_y"][wgt_mask_no_quench],
                        z1=halos["halo_z"][wgt_mask_no_quench],
                        w1=w_nq[wgt_mask_no_quench],
                        w1_jac=dw_nq[:, wgt_mask_no_quench],
                        inside_subvol=halos["_inside_subvol"][wgt_mask_no_quench],
                        rpbins=rpbins,
                        zmax=zmax,
                        boxsize=box_length
)

if RANK == 0:
    print("goal wprp done", flush=True)
    print(gq.shape, gnq.shape)

# 3) do optimization
theta_init = np.copy(theta)

# copy necessary params into static_params arrray
static_params = [
                 rpwp_q_goal, rpwp_nq_goal,
                 halos["logmpeak"], halos["loghost_mpeak"], halos["vmax_frac"],
                 halos["halo_x"], halos["halo_y"], halos["halo_z"],
                 halos["upid"], halos["_inside_subvol"], halos["time_since_infall"],
                 idx_to_deposit,
                 rpbins,
                 mass_bin_edges[0],
                 mass_bin_edges[1],
                 zmax,
                 box_length
]

theta, error_history = adam(
                        static_params,
                        theta,
                        maxiter=5,
                        minerr=4.0,
                        err_func=mse_rpwp_quench_adam_wrapper
)

# 4) Make figures

# calculate wprp with initial theta parameters
w_q, dw_q, w_nq, dw_nq = compute_weight_and_jac_quench(
                    halos["logmpeak"],
                    halos["loghost_mpeak"],
                    halos["logvmax_frac"],
                    halos["upid"],
                    halos["time_since_infall"],
                    idx_to_deposit,
                    mass_bin_edges[0], mass_bin_edges[1],
                    theta_init
)

wgt_mask_quench = w_q > 0
wgt_mask_no_quench = w_nq > 0

rpwp_q_init, _ = compute_rpwp(
                    x1=halos["halo_x"][wgt_mask_quench],
                    y1=halos["halo_y"][wgt_mask_quench],
                    z1=halos["halo_z"][wgt_mask_quench],
                    w1=w_q[wgt_mask_quench],
                    w1_jac=dw_q[:, wgt_mask_quench],
                    inside_subvol=halos["_inside_subvol"][wgt_mask_quench],
                    rpbins=rpbins,
                    zmax=zmax,
                    boxsize=box_length
)

rpwp_nq_init, _ = compute_rpwp(
                    x1=halos["halo_x"][wgt_mask_no_quench],
                    y1=halos["halo_y"][wgt_mask_no_quench],
                    z1=halos["halo_z"][wgt_mask_no_quench],
                    w1=w_nq[wgt_mask_no_quench],
                    w1_jac=dw_nq[:, wgt_mask_no_quench],
                    inside_subvol=halos["_inside_subvol"][wgt_mask_no_quench],
                    rpbins=rpbins,
                    zmax=zmax,
                    boxsize=box_length
)

# calculate wprp with final theta parameters
w_q, dw_q, w_nq, dw_nq = compute_weight_and_jac_quench(
                    halos["logmpeak"],
                    halos["loghost_mpeak"],
                    halos["logvmax_frac"],
                    halos["upid"],
                    halos["time_since_infall"],
                    idx_to_deposit,
                    mass_bin_edges[0], mass_bin_edges[1],
                    theta
)

wgt_mask_quench = w_q > 0
wgt_mask_no_quench = w_nq > 0

rpwp_q, _ = compute_rpwp(
                    x1=halos["halo_x"][wgt_mask_quench],
                    y1=halos["halo_y"][wgt_mask_quench],
                    z1=halos["halo_z"][wgt_mask_quench],
                    w1=w_q[wgt_mask_quench],
                    w1_jac=dw_q[:, wgt_mask_quench],
                    inside_subvol=halos["_inside_subvol"][wgt_mask_quench],
                    rpbins=rpbins,
                    zmax=zmax,
                    boxsize=box_length
)

rpwp_nq, _ = compute_rpwp(
                    x1=halos["halo_x"][wgt_mask_no_quench],
                    y1=halos["halo_y"][wgt_mask_no_quench],
                    z1=halos["halo_z"][wgt_mask_no_quench],
                    w1=w_nq[wgt_mask_no_quench],
                    w1_jac=dw_nq[:, wgt_mask_no_quench],
                    inside_subvol=halos["_inside_subvol"][wgt_mask_no_quench],
                    rpbins=rpbins,
                    zmax=zmax,
                    boxsize=box_length
)

# error history figure
if RANK == 0:
    fig = plt.figure(figsize=(12,8), facecolor="w")

    plt.plot(error_history)

    plt.xlabel("Iteration Number", fontsize=16)
    plt.ylabel("Mean Squared Error", fontsize=16)
    plt.title("Error per Iteration", fontsize=20)

    plt.tight_layout()
    plt.savefig("wprp_error_history.png")

# rpwp figure
if RANK == 0:
    fig, axs = plt.subplots(1,2, figsize=(16,8), facecolor="w")

    # quenched
    axs[0].plot(rpbins[:-1], rpwp_q_init, linewidth=4)
    axs[0].plot(rpbins[:-1], rpwp_q, linewidth=4)
    axs[0].plot(rpbins[:-1], rpwp_q_goal, linewidth=4)

    axs[0].legend(["Initial Guess", "Final Guess", "Goal"])

    axs[0].set_xlabel("rp", fontsize=16)
    axs[0].set_ylabel("rp wp(rp)", fontsize=16)
    axs[0].set_title("Quenched Correlation Function", fontsize=20)

    # un quenched
    axs[1].plot(rpbins[:-1], rpwp_nq_init, linewidth=4)
    axs[1].plot(rpbins[:-1], rpwp_nq, linewidth=4)
    axs[1].plot(rpbins[:-1], rpwp_nq_goal, linewidth=4)

    axs[1].set_xlabel("rp", fontsize=16)
    axs[1].set_ylabel("rp wp(rp)", fontsize=16)
    axs[1].set_title("Unquenched Correlation Function", fontsize=20)

    plt.savefig("rpwp_quench_opt.png")

