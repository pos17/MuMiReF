import numpy as np
import sound_field_analysis as sfa
"""
# Define microphone capsule positions (azimuth and elevation angles in radians)
microphone_positions = np.array([(0.0, np.pi/4), (np.pi / 2, np.pi/4), (np.pi, np.pi/4), (3 * np.pi / 2, np.pi/4), (np.pi/4, -np.pi/4), (3* np.pi / 4, -np.pi/4), (5* np.pi / 4, -np.pi/4), (7* np.pi / 4,- np.pi/4)])


# Set the desired Ambisonic order
order = 2

# Initialize an array to store the quadrature weights
quadrature_weights = []

# Compute the quadrature weights
for l in range(order + 1):
    for m in range(-l, l + 1):
        # Calculate the spherical harmonic for the given (l, m) term
        sph_harm = sfa.sph.sph_harm(l, m, microphone_positions[1,0],microphone_positions[1,1],kind="real")
        
        # Integrate to compute the quadrature weight
        weight = np.sum(np.abs(sph_harm) ** 2) / len(microphone_positions)
        
        # Append the weight to the weights array
        quadrature_weights.append(weight)

# The 'quadrature_weights' array now contains the computed weights
"""

points = sfa.gen.gauss_grid(4,2)

print("done")