"""A verbatim port of ``calc_all_features_v3`` from the physics group's core.py.

``reference_ipynb_notebooks/core.py`` imports TensorFlow, UMAP and XGBoost at
module level, so the tests cannot import it. The feature function itself
(core.py:459-574) needs only NumPy and pandas, and is copied here line for
line - the tqdm progress bar dropped, the Hungarian comments translated - so
the synthetic aggregated fixture is written by the producer's own arithmetic,
and Group-1 parity is checked against it rather than against a second reading
of the formulas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calc_all_features_v3(df: pd.DataFrame) -> pd.DataFrame:
    event_metrics = []
    eps = 1e-6

    # The geometric metrics of one (x, y, z) triple: the box, the spherical
    # values and the centroids, returned with a key prefix.
    def get_spatial_metrics(x, y, z, energy, total_energy, prefix=""):
        min_x, max_x = x.min(), x.max()
        min_y, max_y = y.min(), y.max()
        min_z, max_z = z.min(), z.max()

        width = max(max_x - min_x, eps)
        height = max(max_y - min_y, eps)
        depth = max(max_z, eps)
        depth_range = max(max_z - min_z, eps)
        volume = width * height * depth

        r = np.sqrt(x**2 + y**2 + z**2)
        r_sum = r.sum()

        if r_sum > 0:
            theta = np.arccos(np.clip(z / np.where(r == 0, eps, r), -1, 1))
            phi = np.arctan2(y, x)
            mean_r, std_r, max_r = r.mean(), r.std(), r.max()
        else:
            theta = phi = np.zeros_like(r)
            mean_r = std_r = max_r = 0

        if total_energy > 0:
            weighted_r_mean = (r * energy).sum() / total_energy
            avg_theta, avg_phi = theta.mean(), phi.mean()
            centroid_x = (x * energy).sum() / total_energy
            centroid_y = (y * energy).sum() / total_energy
            centroid_z = (z * energy).sum() / total_energy
        else:
            weighted_r_mean = mean_r
            avg_theta, avg_phi = 0, 0
            centroid_x, centroid_y, centroid_z = x.mean(), y.mean(), z.mean()

        angular_spread = theta.std() + phi.std()

        p = prefix
        return {
            f'width{p}': width, f'height{p}': height, f'depth{p}': depth,
            f'depth_range{p}': depth_range, f'volume{p}': volume,
            f'centroid_x{p}': centroid_x, f'centroid_y{p}': centroid_y, f'centroid_z{p}': centroid_z,
            f'mean_r{p}': mean_r, f'std_r{p}': std_r, f'max_r{p}': max_r,
            f'weighted_r_mean{p}': weighted_r_mean,
            f'avg_theta{p}': avg_theta, f'avg_phi{p}': avg_phi, f'angular_spread{p}': angular_spread
        }

    for event_id, group in df.groupby('event_number'):
        energies = group['energy'].to_numpy()
        num_hits = len(energies)
        energy = group['energy']
        total_hit_energy = energy.sum()

        inc_m = group['incoming_momentum'].iloc[0] if 'incoming_momentum' in group.columns else None
        inc_theta = group['incoming_theta'].iloc[0] if 'incoming_theta' in group.columns else None
        inc_phi = group['incoming_phi'].iloc[0] if 'incoming_phi' in group.columns else None
        inc_m_bin = group['incoming_momentum_bin'].iloc[0] if 'incoming_momentum_bin' in group.columns else None

        base_metrics = {
            'event_id': event_id,
            'incoming_momentum': inc_m,
            'incoming_theta': inc_theta,
            'incoming_phi': inc_phi,
            'incoming_momentum_bin': inc_m_bin,
            'num_hits': num_hits,
            'total_hit_energy': total_hit_energy,
        }

        # 1. Global (absolute) metrics.
        spatial_global = get_spatial_metrics(group['x'], group['y'], group['z'], energy, total_hit_energy, prefix="")

        # 2. Translated metrics (shift only).
        if 'x_trans' in group.columns:
            spatial_trans = get_spatial_metrics(group['x_trans'], group['y_trans'], group['z_trans'], energy, total_hit_energy, prefix="_trans")
        else:
            spatial_trans = {}

        # 3. Local metrics (shift and rotation).
        if 'x_local' in group.columns:
            spatial_local = get_spatial_metrics(group['x_local'], group['y_local'], group['z_local'], energy, total_hit_energy, prefix="_local")
        else:
            spatial_local = {}

        final_event_metrics = {**base_metrics, **spatial_global, **spatial_trans, **spatial_local}
        event_metrics.append(final_event_metrics)

    event_metrics_df = pd.DataFrame(event_metrics)

    event_metrics_df['numerical_density'] = event_metrics_df['num_hits'] / event_metrics_df['volume']
    event_metrics_df['energy_density'] = event_metrics_df['total_hit_energy'] / event_metrics_df['volume']

    if 'volume_trans' in event_metrics_df.columns:
        event_metrics_df['numerical_density_trans'] = event_metrics_df['num_hits'] / event_metrics_df['volume_trans']
        event_metrics_df['energy_density_trans'] = event_metrics_df['total_hit_energy'] / event_metrics_df['volume_trans']

    if 'volume_local' in event_metrics_df.columns:
        event_metrics_df['numerical_density_local'] = event_metrics_df['num_hits'] / event_metrics_df['volume_local']
        event_metrics_df['energy_density_local'] = event_metrics_df['total_hit_energy'] / event_metrics_df['volume_local']

    return event_metrics_df
