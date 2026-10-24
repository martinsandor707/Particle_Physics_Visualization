import time
import umap
import copy
import random
import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
import seaborn as sns
import tensorflow as tf
import matplotlib.pyplot as plt

from tqdm import tqdm

from sklearn.metrics import r2_score
from sklearn.metrics import log_loss
from sklearn.metrics import f1_score
from sklearn.metrics import recall_score
from sklearn.metrics import accuracy_score
from sklearn.metrics import precision_score
from sklearn.metrics import confusion_matrix
from sklearn.metrics import balanced_accuracy_score
from sklearn.metrics import top_k_accuracy_score
from sklearn.metrics import mean_absolute_error
from sklearn.metrics import mean_squared_error
from sklearn.metrics import root_mean_squared_error

from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest

from sklearn.preprocessing import LabelEncoder
from sklearn.preprocessing import StandardScaler
from sklearn.preprocessing import MinMaxScaler

from sklearn.model_selection import KFold
from sklearn.model_selection import StratifiedKFold
from sklearn.model_selection import train_test_split
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis as LDA

from scipy import sparse
from scipy.stats import entropy
from scipy.special import softmax
from scipy.stats import gaussian_kde
from scipy.spatial.distance import cdist
from scipy.spatial.distance import jensenshannon

from tensorflow.keras.preprocessing.sequence import pad_sequences

SHIFT_Z = 3649
CONTRIBUTION_TIME_MAX = 100000

def shifted_z(df):
    df["z"] = df["z"].apply(lambda z: z-SHIFT_Z)
    return df

def calculate_event_local_coordinates(df, angles_in_degrees=False):
    """
    Kiszámolja a részecskezáporok eltolt (transzlált) és teljes lokális 
    (transzlált + rotált) koordinátáit eseményenként (event_number).
    
    Létrehozott új oszlopok:
    - Csak transzláció: 'x_trans', 'y_trans', 'z_trans'
    - Transzláció + rotáció: 'x_local', 'y_local', 'z_local'
    """
    # Ne módosítsuk az eredeti adatbázist
    df_out = df.copy()

    # --- 1. LÉPÉS: z0 meghatározása (min z eseményenként) ---
    df_out['z0'] = df_out.groupby('event_number')['z'].transform('min')

    # --- 2. LÉPÉS: x0 és y0 meghatározása az első réteg alapján ---
    first_layer = df_out[df_out['z'] == df_out['z0']].copy()

    first_layer['x_times_E'] = first_layer['x'] * first_layer['energy']
    first_layer['y_times_E'] = first_layer['y'] * first_layer['energy']

    origins = first_layer.groupby('event_number')[['x_times_E', 'y_times_E', 'energy']].sum()

    origins['x0'] = origins['x_times_E'] / origins['energy']
    origins['y0'] = origins['y_times_E'] / origins['energy']

    origins = origins[['x0', 'y0']]
    df_out = df_out.merge(origins, on='event_number', how='left')

    # --- 3. LÉPÉS: Translation (Eltolás) ---
    # Itt hozzuk létre a különálló transzlált koordinátákat
    df_out['x_trans'] = df_out['x'] - df_out['x0']
    df_out['y_trans'] = df_out['y'] - df_out['y0']
    df_out['z_trans'] = df_out['z'] - df_out['z0']

    # --- 4. LÉPÉS: Rotation (Forgatás) ---
    theta = df_out['incoming_theta']
    phi = df_out['incoming_phi']

    if angles_in_degrees:
        theta = np.radians(theta)
        phi = np.radians(phi)

    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    cos_p = np.cos(phi)
    sin_p = np.sin(phi)

    # A transzlált értékeket forgatjuk el a saját koordináta-rendszerbe
    dx = df_out['x_trans']
    dy = df_out['y_trans']
    dz = df_out['z_trans']

    df_out['x_local'] = dx * cos_t * cos_p + dy * cos_t * sin_p - dz * sin_t
    df_out['y_local'] = -dx * sin_p + dy * cos_p
    df_out['z_local'] = dx * sin_t * cos_p + dy * sin_t * sin_p + dz * cos_t

    # Takarítás: A segédoszlopokat eldobhatjuk
    df_out = df_out.drop(columns=['x0', 'y0', 'z0'])

    return df_out

def create_sequence(df, incident_energy=None, column_proton_energy=None, short_val=None):
    # 1. Először rendezzük a teljes dataframe-et. 
    # Ez hatékonyabb, mint csoportonként apply-al rendezgetni.
    df_sorted = df.sort_values(['event_id', short_val])
    
    # 2. Csoportosítás eseményazonosító szerint
    grouped = df_sorted.groupby('event_id')

    # 3. Szekvenciák létrehozása (x, y, z, hit_energy tuple listák)
    # A sequences indexe az event_id lesz
    sequences = grouped.apply(lambda x: list(zip(x['x'], x['y'], x['z'], x['hit_energy'])))

    # 4. Energia meghatározása
    if column_proton_energy is not None:
        # Ha megadtuk az oszlopot, kivesszük az első értéket minden eseményhez (redundancia kiszűrése)
        # Ez egy Series-t ad, ahol az index az event_id, az érték pedig az energia
        energy_series = grouped[column_proton_energy].first()
    else:
        # Ha fix értéket kaptunk (incident_energy), azt használjuk
        energy_series = incident_energy
    
    # 5. Új DataFrame összeállítása
    # A pandas automatikusan illeszti az indexeket (event_id alapján)
    processed_df = pd.DataFrame({
        'event_id': sequences.index,
        'sequence': sequences.values,
        'energy_level': energy_series.values if column_proton_energy is not None else energy_series
    }).reset_index(drop=True)

    return processed_df

def generate_physical_soft_labels_from_results(y_encoded, aggregated_kl):
    """
    y_encoded: A rekordok kódolt címkéi (pl. 0, 1, 2...)
    aggregated_kl: A már összesített KL mátrix.
    Visszaadja a rekordokhoz tartozó "puha" címkéket és a template mátrixot.
    """
    
    # 2. Hasonlósági mátrix számítása (exp(-KL))
    # Ez a mérésből adódó közvetlen statisztikai átfedést tükrözi
    # Nincs temperature paraméter, a tiszta fizikai mérést használjuk
    similarity_matrix = np.exp(-aggregated_kl)
    
    # 3. Normalizálás soronként (hogy valószínűségi eloszlást kapjunk)
    # template_matrix[i, j] = P(osztály_j | valóság_i)
    template_matrix = similarity_matrix / similarity_matrix.sum(axis=1)[:, None]
    
    # 4. A rekordokhoz hozzárendeljük a nekik megfelelő "puha" eloszlást
    soft_labels = template_matrix[y_encoded]
    
    return soft_labels

def calculate_kl_jl_metrics(df, feature, label_col):
    # Energiák sorba rendezése numerikusan
    labels = sorted(df[label_col].unique())
    n_labels = len(labels)
    
    # Mátrixok inicializálása
    js_matrix = np.zeros((n_labels, n_labels))
    kl_matrix = np.zeros((n_labels, n_labels))
    
    # Közös rács (grid) az eloszlások kiértékeléséhez
    x_min, x_max = df[feature].min(), df[feature].max()
    # Ha a min és max egyenlő, eltoljuk őket kicsit, hogy a linspace ne dőljön össze
    if x_min == x_max:
        x_min -= 0.1
        x_max += 0.1
    
    x_eval = np.linspace(x_min, x_max, 1000)
    
    pdfs = {}
    epsilon = 1e-10 # A KL-divergencia miatti nullával való osztás elkerülésére
    
    for label in labels:
        subset = df[df[label_col] == label][feature].dropna()
        
        # Ellenőrizzük, hogy van-e elég adat és van-e szórás
        if len(subset) > 1 and np.var(subset) > 1e-12:
            try:
                kde = gaussian_kde(subset)
                pdf = kde(x_eval)
            except np.linalg.LinAlgError:
                # Ha mégis beütne a szinguláris mátrix hiba, adunk hozzá egy kis zajt
                jitter = np.random.normal(0, 1e-10, size=subset.shape)
                kde = gaussian_kde(subset + jitter)
                pdf = kde(x_eval)
        else:
            # Ha nincs variancia vagy kevés az adat, egy Dirac-szerű tüskét imitálunk
            # (Vagy egyenletes eloszlást, ha az biztonságosabb a modelledben)
            pdf = np.zeros_like(x_eval)
            # Megkeressük a legközelebbi pontot a rácson a konstans értékhez
            val = subset.iloc[0] if len(subset) > 0 else (x_min + x_max) / 2
            idx = np.abs(x_eval - val).argmin()
            pdf[idx] = 1.0

        # Normalizálás és simítás (epsilon), hogy ne legyen 0 érték
        pdf = (pdf + epsilon) / np.sum(pdf + epsilon)
        pdfs[label] = pdf

    for i in range(n_labels):
        for j in range(n_labels):
            p = pdfs[labels[i]]
            q = pdfs[labels[j]]
            
            # Jensen-Shannon távolság
            js_matrix[i, j] = jensenshannon(p, q)
            
            # KL-divergencia: D_KL(P || Q)
            kl_matrix[i, j] = entropy(p, q)
            
    js_df = pd.DataFrame(js_matrix, index=labels, columns=labels)
    kl_df = pd.DataFrame(kl_matrix, index=labels, columns=labels)
    
    return js_df, kl_df

def run_kl_jl_analysis(df, features, label_col='incident_energy', verbose=True):
    all_kl_results = {}
    total_js_matrix = None
    valid_features_count = 0

    for feat in features:
        try:
            js_df, kl_df = calculate_kl_jl_metrics(df, feat, label_col)
            all_kl_results[feat] = kl_df
            
            if total_js_matrix is None:
                total_js_matrix = js_df.copy()
            else:
                total_js_matrix += js_df
            valid_features_count += 1
        except Exception as e:
            if verbose:
                print(f"Hiba a(z) {feat} jellemzőnél: {e}")
            continue
            
    if valid_features_count == 0:
        print("Nincs feldolgozható jellemző.")
        return None, None

    # Átlagoljuk a JS mátrixot
    avg_js_matrix = total_js_matrix / valid_features_count

    if verbose:
        plt.figure(figsize=(10, 7))
        sns.heatmap(avg_js_matrix, annot=True, cmap="YlOrRd", fmt=".3f")
        plt.title(f"Átlagos Jensen-Shannon távolság ({valid_features_count} jellemző alapján)")
        plt.show()

        print("\n--- KL-Divergencia értékek ---")
        for feat, kl_df in all_kl_results.items():
            print(f"\nJellemző: {feat}")
            print(kl_df.round(4))
            print("-" * 30)

    return all_kl_results, avg_js_matrix

def identify_anomalies(df, feature_columns):
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df[feature_columns])

    # --- 3. Vizualizáció PCA-val ---
    reducer = umap.UMAP(n_neighbors=30, min_dist=0.1, n_components=2, random_state=42)
    X_umap = reducer.fit_transform(X_scaled) # Használd a már log-skálázott X_scaled-et!

    df['umap1'] = X_umap[:, 0]
    df['umap2'] = X_umap[:, 1]

# def to_spherical_coord(event_data):
#     # event_data egy (N, 3) alakú tömb, ahol N tetszőleges
#     x = event_data[:, 0]
#     y = event_data[:, 1]
#     z = event_data[:, 2]

#     r = np.sqrt(x**2 + y**2 + z**2)
#     phi = np.arctan2(y, x)
#     theta = np.arccos(z / r)

#     # Visszatérünk egy (N, 3) alakú tömbbel, de már gömbi koordinátákban
#     return np.column_stack((phi, theta, r))

# import numpy as np

def to_spherical_coord(event_data):
    # event_data egy (N, 3) alakú tömb, ahol N tetszőleges
    x = event_data[:, 0]
    y = event_data[:, 1]
    z = event_data[:, 2]

    r = np.sqrt(x**2 + y**2 + z**2)
    phi = np.arctan2(y, x)
    
    # 1. Nullával osztás elkerülése: ahol r nulla, ott egy átmeneti 1.0-val osztunk
    safe_r = np.where(r == 0, 1.0, r)
    
    # 2. Lebegőpontos pontatlanságok kiküszöbölése (-1 és 1 közé vágjuk az értéket)
    ratio = np.clip(z / safe_r, -1.0, 1.0)
    
    # 3. Kiszámoljuk a theta-t. Ahol eredetileg r == 0 volt, ott a theta-t kényszerítjük 0-ra.
    theta = np.where(r == 0, 0.0, np.arccos(ratio))

    # Visszatérünk egy (N, 3) alakú tömbbel, de már gömbi koordinátákban
    return np.column_stack((phi, theta, r))

def calc_spherical_coords(df):
    """
    Kiszámítja és hozzáadja a gömbi koordinátákat (phi, theta, r)
    az abszolút (x, y, z), a transzlált (x_trans, y_trans, z_trans)
    és a lokális (x_local, y_local, z_local) koordinátákra is.
    """
    # 1. Abszolút (globális) koordináták
    if all(col in df.columns for col in ['x', 'y', 'z']):
        coords_abs = to_spherical_coord(df[['x', 'y', 'z']].values)
        df['phi'] = coords_abs[:, 0]
        df['theta'] = coords_abs[:, 1]
        df['r'] = coords_abs[:, 2]

    # 2. Transzlált koordináták
    if all(col in df.columns for col in ['x_trans', 'y_trans', 'z_trans']):
        coords_trans = to_spherical_coord(df[['x_trans', 'y_trans', 'z_trans']].values)
        df['phi_trans'] = coords_trans[:, 0]
        df['theta_trans'] = coords_trans[:, 1]
        df['r_trans'] = coords_trans[:, 2]

    # 3. Lokális (transzlált + rotált) koordináták
    if all(col in df.columns for col in ['x_local', 'y_local', 'z_local']):
        coords_local = to_spherical_coord(df[['x_local', 'y_local', 'z_local']].values)
        df['phi_local'] = coords_local[:, 0]
        df['theta_local'] = coords_local[:, 1]
        df['r_local'] = coords_local[:, 2]

    return df

def process_event_data(df, incident_energy=None, column_proton_energy=None, event_id_col='event_id'):
    event_metrics = []
    # Epsilon: egy nagyon kicsi érték (pl. 0.001 mm vagy a detektor egysége), 
    # hogy elkerüljük a nullával való osztást.
    eps = 1e-6 

    for event_id, group in tqdm(df.groupby(event_id_col)):
        x, y, z = group['x'], group['y'], group['z']
        energy = group['hit_energy']
        total_hit_energy = energy.sum()

        # --- Descartes-féle alapértékek ---
        min_x, max_x = x.min(), x.max()
        min_y, max_y = y.min(), y.max()
        min_z, max_z = z.min(), z.max()

        # Biztosítjuk, hogy a kiterjedés legalább eps legyen
        width = max(max_x - min_x, eps)
        height = max(max_y - min_y, eps)
        # Ha a mélység fix (pl. z=0-tól mérjük), akkor max_z, 
        # de ha csak a felhő vastagsága számít, akkor max_z - min_z.
        depth = max(max_z, eps) 
        depth_range = max(max_z - min_z, eps)

        volume = width * height * depth

        # --- Gömbi koordináták kiszámítása ---
        # r: távolság az origótól
        # r kiszámításánál is érdemes figyelni:
        r = np.sqrt(x**2 + y**2 + z**2)
        # r_sum ellenőrzése a nullával osztás ellen arccos-nál
        r_sum = r.sum()
        
        if r_sum > 0:
            # A clip fontos, hogy a lebegőpontos hiba miatt ne legyen > 1 az érték
            theta = np.arccos(np.clip(z / np.where(r==0, eps, r), -1, 1))
            phi = np.arctan2(y, x)
            mean_r = r.mean()
            std_r = r.std()
            max_r = r.max()
        else:
            theta = np.zeros_like(r)
            phi = np.zeros_like(r)
            mean_r, std_r, max_r = 0, 0, 0

        # --- Gömbi aggregációk (skalár értékek) ---
        mean_r = r.mean()
        std_r = r.std()
        max_r = r.max()
        
        # Energia-súlyozott sugár (hol van a "bragg-peak" vagy az energia súlypontja távolságban)
        if total_hit_energy > 0:
            weighted_r_mean = (r * energy).sum() / total_hit_energy
            # Irányultság: az esemény átlagos szöge
            avg_theta = theta.mean() 
            avg_phi = phi.mean()
        else:
            weighted_r_mean = mean_r
            avg_theta, avg_phi = 0, 0

        # Szögirányú kiterjedés (szórás) - mennyire "szétterült" az esemény
        angular_spread = theta.std() + phi.std()

        # Centroid (Descartes)
        if total_hit_energy > 0:
            centroid_x = (x * energy).sum() / total_hit_energy
            centroid_y = (y * energy).sum() / total_hit_energy
            centroid_z = (z * energy).sum() / total_hit_energy
        else:
            centroid_x, centroid_y, centroid_z = x.mean(), y.mean(), z.mean()

        if column_proton_energy is None:
            proton_energy = incident_energy
        else:
            proton_energy = group[column_proton_energy].iloc[0]

        event_metrics.append({
            'event_id': event_id,
            'incident_energy': proton_energy,
            'width': width,
            'height': height,
            'depth': depth,
            'depth_range': depth_range,
            'volume': volume,
            'num_hits': len(group),
            'total_hit_energy': total_hit_energy,
            'centroid_x': centroid_x,
            'centroid_y': centroid_y,
            'centroid_z': centroid_z,
            # Új gömbi mérőszámok:
            'mean_r': mean_r,               # Átlagos távolság az origótól
            'std_r': std_r,                 # Radiális szórás (felhő vastagsága)
            'max_r': max_r,                 # Legtávolabbi pont
            'weighted_r_mean': weighted_r_mean, # Energia-súlyozott mélység
            'avg_theta': avg_theta,         # Átlagos polárszög (szóródás szöge)
            'avg_phi': avg_phi,             # Átlagos azimut (oldalirány)
            'angular_spread': angular_spread # Mennyire "kúpszerű" a felhő
        })

    event_metrics_df = pd.DataFrame(event_metrics)
    event_metrics_df['numerical_density'] = event_metrics_df['num_hits'] / event_metrics_df['volume']
    event_metrics_df['energy_density'] = event_metrics_df['total_hit_energy'] / event_metrics_df['volume']

    return event_metrics_df

# --- ÚJ: Logikai operátor segédfüggvény a NumPy-hoz
def cond_lt(x, y):
    return np.where(x < y, 1.0, 0.0)

def calc_all_features_v3(df):
    event_metrics = []
    eps = 1e-6 

    # --- Belső segédfüggvény a geometriai metrikák számításához ---
    # Ez kiszámolja egy adott (x, y, z) koordináta-hármasra a dobozt, 
    # a gömbi értékeket és a súlypontokat, majd prefix-szel ellátva adja vissza.
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
            theta = np.arccos(np.clip(z / np.where(r==0, eps, r), -1, 1))
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

        # Prefix (pl. "_local") hozzáadása a kulcsokhoz
        p = prefix
        return {
            f'width{p}': width, f'height{p}': height, f'depth{p}': depth,
            f'depth_range{p}': depth_range, f'volume{p}': volume,
            f'centroid_x{p}': centroid_x, f'centroid_y{p}': centroid_y, f'centroid_z{p}': centroid_z,
            f'mean_r{p}': mean_r, f'std_r{p}': std_r, f'max_r{p}': max_r,
            f'weighted_r_mean{p}': weighted_r_mean, 
            f'avg_theta{p}': avg_theta, f'avg_phi{p}': avg_phi, f'angular_spread{p}': angular_spread
        }

    # =========================================================================
    # FŐ CIKLUS
    # =========================================================================
    for event_id, group in tqdm(df.groupby('event_number')):
        energies = group['energy'].to_numpy()
        num_hits = len(energies)
        energy = group['energy']
        total_hit_energy = energy.sum()

        # Alap metrikák (szögfüggetlen, globális tulajdonságok)
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

        # 1. Globális (abszolút) metrikák
        spatial_global = get_spatial_metrics(group['x'], group['y'], group['z'], energy, total_hit_energy, prefix="")
        
        # 2. Transzlált metrikák (csak eltolás)
        if 'x_trans' in group.columns:
            spatial_trans = get_spatial_metrics(group['x_trans'], group['y_trans'], group['z_trans'], energy, total_hit_energy, prefix="_trans")
        else:
            spatial_trans = {}

        # 3. Lokális metrikák (eltolás + forgatás)
        if 'x_local' in group.columns:
            spatial_local = get_spatial_metrics(group['x_local'], group['y_local'], group['z_local'], energy, total_hit_energy, prefix="_local")
        else:
            spatial_local = {}

        # --- Esemény metrikák összefűzése ---
        # A GNN metrikák kikerültek a szótárak egyesítéséből
        final_event_metrics = {**base_metrics, **spatial_global, **spatial_trans, **spatial_local}
        event_metrics.append(final_event_metrics)

    event_metrics_df = pd.DataFrame(event_metrics)
    
    # --- Sűrűség metrikák kiszámítása minden térben ---
    # Globális sűrűségek
    event_metrics_df['numerical_density'] = event_metrics_df['num_hits'] / event_metrics_df['volume']
    event_metrics_df['energy_density'] = event_metrics_df['total_hit_energy'] / event_metrics_df['volume']
    
    # Transzlált sűrűségek
    if 'volume_trans' in event_metrics_df.columns:
        event_metrics_df['numerical_density_trans'] = event_metrics_df['num_hits'] / event_metrics_df['volume_trans']
        event_metrics_df['energy_density_trans'] = event_metrics_df['total_hit_energy'] / event_metrics_df['volume_trans']
        
    # Lokális sűrűségek (Ezek a legpontosabbak, mert ez a zápor valós térfogatát és sűrűségét adja)
    if 'volume_local' in event_metrics_df.columns:
        event_metrics_df['numerical_density_local'] = event_metrics_df['num_hits'] / event_metrics_df['volume_local']
        event_metrics_df['energy_density_local'] = event_metrics_df['total_hit_energy'] / event_metrics_df['volume_local']

    return event_metrics_df

# def calc_all_features_v2(df):
#     event_metrics = []
#     # Epsilon: egy nagyon kicsi érték (pl. 0.001 mm vagy a detektor egysége), 
#     # hogy elkerüljük a nullával való osztást.
#     eps = 1e-6 

#     for event_id, group in tqdm(df.groupby('event_number')):
#         # --- Koordináták és energiák előkészítése mátrixos műveletekhez
#         pos = group[['x', 'y', 'z']].to_numpy()
#         energies = group['energy'].to_numpy()
#         num_hits = len(energies)

#         x, y, z = group['x'], group['y'], group['z']
#         energy = group['energy']
#         total_hit_energy = energy.sum()

#         # --- Descartes-féle alapértékek ---
#         min_x, max_x = x.min(), x.max()
#         min_y, max_y = y.min(), y.max()
#         min_z, max_z = z.min(), z.max()

#         # Biztosítjuk, hogy a kiterjedés legalább eps legyen
#         width = max(max_x - min_x, eps)
#         height = max(max_y - min_y, eps)
#         depth = max(max_z, eps) 
#         depth_range = max(max_z - min_z, eps)

#         volume = width * height * depth

#         # --- Gömbi koordináták kiszámítása ---
#         r = np.sqrt(x**2 + y**2 + z**2)
#         r_sum = r.sum()
        
#         if r_sum > 0:
#             theta = np.arccos(np.clip(z / np.where(r==0, eps, r), -1, 1))
#             phi = np.arctan2(y, x)
#             mean_r = r.mean()
#             std_r = r.std()
#             max_r = r.max()
#         else:
#             theta = np.zeros_like(r)
#             phi = np.zeros_like(r)
#             mean_r, std_r, max_r = 0, 0, 0

#         # =========================================================================
#         # --- GNN TOPOLÓGIAI LEPÁRLÁS (PÁRONKÉNTI INTERAKCIÓK) ---
#         # =========================================================================
#         if num_hits >= 2:
#             dist_matrix = cdist(pos, pos, metric='euclidean')
#             e_src_matrix = np.tile(energies.reshape(-1, 1), (1, num_hits))
            
#             e_cond_1 = cond_lt(dist_matrix * -0.11950035, -5.9740586)
#             e_cond_2 = cond_lt(dist_matrix * 0.076865606, 4.447341)
#             edge_msgs_log = (((((2.7901795 * 1.0320415) * e_cond_1) + -6.477164) * e_cond_2) + -0.037561912) - e_src_matrix
            
#             d1_denom = np.square(-29.211584 + dist_matrix)
#             d2_denom = dist_matrix - np.sqrt(dist_matrix + 1e-8)
#             edge_msgs_arith = ((dist_matrix * -30.439938) / np.where(d1_denom == 0, eps, d1_denom)) - \
#                               ((-29.211584 / np.where(d2_denom == 0, eps, d2_denom)) + 0.014171418)
            
#             np.fill_diagonal(edge_msgs_log, 0)
#             np.fill_diagonal(edge_msgs_arith, 0)
            
#             msg_sum_log = edge_msgs_log.sum(axis=0)
#             msg_sum_arith = edge_msgs_arith.sum(axis=0)
            
#             node_up_log = (msg_sum_log * (msg_sum_log + 3.564986)) * \
#                           (((energies * 1.2855072) + -0.054674573) * \
#                           (((energies + -0.006390664) - (msg_sum_log * 9.90654e-5)) - (energies * -0.054674573)))
            
#             node_up_arith = (((msg_sum_arith * np.square(1.7240694)) * energies) - \
#                             np.square(np.square(msg_sum_arith * (-0.012513807 - (energies * (-2.393362 * energies)))))) - -0.38561794
            
#             gnn_logical_feat = node_up_log.mean()
#             gnn_arith_feat = node_up_arith.mean()
#             gnn_msg_log_avg = msg_sum_log.mean()
#             gnn_msg_arith_avg = msg_sum_arith.mean()
#         else:
#             gnn_logical_feat = gnn_arith_feat = gnn_msg_log_avg = gnn_msg_arith_avg = 0
            
#         # =========================================================================

#         # --- Gömbi aggregációk (skalár értékek) ---
#         mean_r = r.mean()
#         std_r = r.std()
#         max_r = r.max()
        
#         if total_hit_energy > 0:
#             weighted_r_mean = (r * energy).sum() / total_hit_energy
#             avg_theta = theta.mean() 
#             avg_phi = phi.mean()
#         else:
#             weighted_r_mean = mean_r
#             avg_theta, avg_phi = 0, 0

#         angular_spread = theta.std() + phi.std()

#         if total_hit_energy > 0:
#             centroid_x = (x * energy).sum() / total_hit_energy
#             centroid_y = (y * energy).sum() / total_hit_energy
#             centroid_z = (z * energy).sum() / total_hit_energy
#         else:
#             centroid_x, centroid_y, centroid_z = x.mean(), y.mean(), z.mean()

#         # --- Globális eseményjellemzők lekérése (biztonságos ellenőrzéssel) ---
#         inc_m = group['incoming_momentum'].iloc[0] if 'incoming_momentum' in group.columns else None
#         inc_theta = group['incoming_theta'].iloc[0] if 'incoming_theta' in group.columns else None
#         inc_phi = group['incoming_phi'].iloc[0] if 'incoming_phi' in group.columns else None
#         inc_m_bin = group['incoming_momentum_bin'].iloc[0] if 'incoming_momentum_bin' in group.columns else None

#         event_metrics.append({
#             'event_id': event_id,
#             'incoming_momentum': inc_m,
#             'incoming_theta': inc_theta,          
#             'incoming_phi': inc_phi,              
#             'incoming_momentum_bin': inc_m_bin,   
#             'width': width,
#             'height': height,
#             'depth': depth,
#             'depth_range': depth_range,
#             'volume': volume,
#             'num_hits': len(group),
#             'total_hit_energy': total_hit_energy,
#             'centroid_x': centroid_x,
#             'centroid_y': centroid_y,
#             'centroid_z': centroid_z,
#             'mean_r': mean_r,               
#             'std_r': std_r,                 
#             'max_r': max_r,                 
#             'weighted_r_mean': weighted_r_mean, 
#             'avg_theta': avg_theta,         
#             'avg_phi': avg_phi,             
#             'angular_spread': angular_spread, 
#             'gnn_logical_node': gnn_logical_feat,
#             'gnn_arith_node': gnn_arith_feat,
#             'gnn_msg_log_sum': gnn_msg_log_avg,
#             'gnn_msg_arith_sum': gnn_msg_arith_avg
#         })

#     event_metrics_df = pd.DataFrame(event_metrics)
#     event_metrics_df['numerical_density'] = event_metrics_df['num_hits'] / event_metrics_df['volume']
#     event_metrics_df['energy_density'] = event_metrics_df['total_hit_energy'] / event_metrics_df['volume']

#     return event_metrics_df

# def calc_all_features(df, incident_energy=None, column_proton_energy=None, event_id_col='event_id'):
#     event_metrics = []
#     # Epsilon: egy nagyon kicsi érték (pl. 0.001 mm vagy a detektor egysége), 
#     # hogy elkerüljük a nullával való osztást.
#     eps = 1e-6 

#     for event_id, group in tqdm(df.groupby(event_id_col)):
#         # --- ÚJ: Koordináták és energiák előkészítése mátrixos műveletekhez
#         pos = group[['x', 'y', 'z']].to_numpy()
#         energies = group['hit_energy'].to_numpy()
#         num_hits = len(energies)

#         x, y, z = group['x'], group['y'], group['z']
#         energy = group['hit_energy']
#         total_hit_energy = energy.sum()

#         # --- Descartes-féle alapértékek ---
#         min_x, max_x = x.min(), x.max()
#         min_y, max_y = y.min(), y.max()
#         min_z, max_z = z.min(), z.max()

#         # Biztosítjuk, hogy a kiterjedés legalább eps legyen
#         width = max(max_x - min_x, eps)
#         height = max(max_y - min_y, eps)
#         # Ha a mélység fix (pl. z=0-tól mérjük), akkor max_z, 
#         # de ha csak a felhő vastagsága számít, akkor max_z - min_z.
#         depth = max(max_z, eps) 
#         depth_range = max(max_z - min_z, eps)

#         volume = width * height * depth

#         # --- Gömbi koordináták kiszámítása ---
#         # r: távolság az origótól
#         # r kiszámításánál is érdemes figyelni:
#         r = np.sqrt(x**2 + y**2 + z**2)
#         # r_sum ellenőrzése a nullával osztás ellen arccos-nál
#         r_sum = r.sum()
        
#         if r_sum > 0:
#             # A clip fontos, hogy a lebegőpontos hiba miatt ne legyen > 1 az érték
#             theta = np.arccos(np.clip(z / np.where(r==0, eps, r), -1, 1))
#             phi = np.arctan2(y, x)
#             mean_r = r.mean()
#             std_r = r.std()
#             max_r = r.max()
#         else:
#             theta = np.zeros_like(r)
#             phi = np.zeros_like(r)
#             mean_r, std_r, max_r = 0, 0, 0

#         # =========================================================================
#         # --- ÚJ: GNN TOPOLÓGIAI LEPÁRLÁS (PÁRONKÉNTI INTERAKCIÓK) ---
#         # =========================================================================
        
#         if num_hits >= 2:
#             # 1. Távolságmátrix kiszámítása (x0 = hit-to-hit távolság)
#             dist_matrix = cdist(pos, pos, metric='euclidean')
            
#             # 2. Edge üzenetek kiszámítása (Vektorizált mátrix műveletek)
#             e_src_matrix = np.tile(energies.reshape(-1, 1), (1, num_hits))
            
#             # --- EDGE ÍTÉLET LOGIKAI (Lépcsős formula)
#             e_cond_1 = cond_lt(dist_matrix * -0.11950035, -5.9740586)
#             e_cond_2 = cond_lt(dist_matrix * 0.076865606, 4.447341)
#             edge_msgs_log = (((((2.7901795 * 1.0320415) * e_cond_1) + -6.477164) * e_cond_2) + -0.037561912) - e_src_matrix
            
#             # --- EDGE ARITMETIKAI (Folytonos formula + biztonsági osztás védelem)
#             d1_denom = np.square(-29.211584 + dist_matrix)
#             d2_denom = dist_matrix - np.sqrt(dist_matrix + 1e-8)
#             edge_msgs_arith = ((dist_matrix * -30.439938) / np.where(d1_denom == 0, eps, d1_denom)) - \
#                               ((-29.211584 / np.where(d2_denom == 0, eps, d2_denom)) + 0.014171418)
            
#             # Self-loops eltávolítása (i == j élek a GNN-ben sincsenek)
#             np.fill_diagonal(edge_msgs_log, 0)
#             np.fill_diagonal(edge_msgs_arith, 0)
            
#             # 3. Aggregáció: Msg_sum kiszámítása minden node-ra (scatter_add megfelelője)
#             msg_sum_log = edge_msgs_log.sum(axis=0)
#             msg_sum_arith = edge_msgs_arith.sum(axis=0)
            
#             # 4. Node frissítési szabályok (x0 = hit_energy, x1 = msg_sum)
#             # --- NODE ÍTÉLET LOGIKAI (Polinom)
#             node_up_log = (msg_sum_log * (msg_sum_log + 3.564986)) * \
#                           (((energies * 1.2855072) + -0.054674573) * \
#                           (((energies + -0.006390664) - (msg_sum_log * 9.90654e-5)) - (energies * -0.054674573)))
            
#             # --- NODE ARITMETIKAI (Hatványos)
#             node_up_arith = (((msg_sum_arith * np.square(1.7240694)) * energies) - \
#                             np.square(np.square(msg_sum_arith * (-0.012513807 - (energies * (-2.393362 * energies)))))) - -0.38561794
            
#             # 5. Global Pooling (global_mean_pool szimulációja az eseményre)
#             gnn_logical_feat = node_up_log.mean()
#             gnn_arith_feat = node_up_arith.mean()
#             gnn_msg_log_avg = msg_sum_log.mean()
#             gnn_msg_arith_avg = msg_sum_arith.mean()
#         else:
#             gnn_logical_feat = gnn_arith_feat = gnn_msg_log_avg = gnn_msg_arith_avg = 0
            
#         # =========================================================================

#         # --- Gömbi aggregációk (skalár értékek) ---
#         mean_r = r.mean()
#         std_r = r.std()
#         max_r = r.max()
        
#         # Energia-súlyozott sugár (hol van a "bragg-peak" vagy az energia súlypontja távolságban)
#         if total_hit_energy > 0:
#             weighted_r_mean = (r * energy).sum() / total_hit_energy
#             # Irányultság: az esemény átlagos szöge
#             avg_theta = theta.mean() 
#             avg_phi = phi.mean()
#         else:
#             weighted_r_mean = mean_r
#             avg_theta, avg_phi = 0, 0

#         # Szögirányú kiterjedés (szórás) - mennyire "szétterült" az esemény
#         angular_spread = theta.std() + phi.std()

#         # Centroid (Descartes)
#         if total_hit_energy > 0:
#             centroid_x = (x * energy).sum() / total_hit_energy
#             centroid_y = (y * energy).sum() / total_hit_energy
#             centroid_z = (z * energy).sum() / total_hit_energy
#         else:
#             centroid_x, centroid_y, centroid_z = x.mean(), y.mean(), z.mean()

#         if column_proton_energy is None:
#             proton_energy = incident_energy
#         else:
#             proton_energy = group[column_proton_energy].iloc[0]


#         event_metrics.append({
#             'event_id': event_id,
#             'incident_energy': proton_energy,
#             'width': width,
#             'height': height,
#             'depth': depth,
#             'depth_range': depth_range,
#             'volume': volume,
#             'num_hits': len(group),
#             'total_hit_energy': total_hit_energy,
#             'centroid_x': centroid_x,
#             'centroid_y': centroid_y,
#             'centroid_z': centroid_z,
#             # Új gömbi mérőszámok:
#             'mean_r': mean_r,               # Átlagos távolság az origótól
#             'std_r': std_r,                 # Radiális szórás (felhő vastagsága)
#             'max_r': max_r,                 # Legtávolabbi pont
#             'weighted_r_mean': weighted_r_mean, # Energia-súlyozott mélység
#             'avg_theta': avg_theta,         # Átlagos polárszög (szóródás szöge)
#             'avg_phi': avg_phi,             # Átlagos azimut (oldalirány)
#             'angular_spread': angular_spread, # Mennyire "kúpszerű" a felhő

#              # --- ÚJ: GNN alapú jellemzők hozzáadása a kimenethez
#             'gnn_logical_node': gnn_logical_feat,
#             'gnn_arith_node': gnn_arith_feat,
#             'gnn_msg_log_sum': gnn_msg_log_avg,
#             'gnn_msg_arith_sum': gnn_msg_arith_avg
#         })

#     event_metrics_df = pd.DataFrame(event_metrics)
#     event_metrics_df['numerical_density'] = event_metrics_df['num_hits'] / event_metrics_df['volume']
#     event_metrics_df['energy_density'] = event_metrics_df['total_hit_energy'] / event_metrics_df['volume']

#     return event_metrics_df

def clean_dataset(df, stats_dict, label_key):
    """Kiszűri az anomáliákat a megadott statisztikák alapján."""
    df_clean = df.copy()
    initial_count = len(df_clean)
    
    for feat in ['volume', 'num_hits']: # A fő hibaforrásokra koncentrálunk
        low, high = stats_dict[feat]
        df_clean = df_clean[(df_clean[feat] >= low) & (df_clean[feat] <= high)]
    
    print(f"{label_key} tisztítása: {initial_count} -> {len(df_clean)} rekord (Törölve: {initial_count - len(df_clean)})")
    return df_clean

def calculate_stats(df, label_key):
    """Kiszámolja a megadott statisztikákat egy adott címkére."""
    stats = {}
    for feat in label_key:
        q1 = df[feat].quantile(0.25)
        q3 = df[feat].quantile(0.75)
        iqr = q3 - q1
        low = q1 - 1.5 * iqr
        high = q3 + 1.5 * iqr
        stats[feat] = (low, high)
    return stats