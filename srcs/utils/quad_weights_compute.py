import numpy as np
from scipy import integrate, special

def spherical_harmonic(theta, phi, l, m):
    return np.real(special.sph_harm(m, l, phi, theta))

def integrate_spherical_harmonics(l, m, sampling_positions):
    # Unpack the sampling positions
    thetas, phis = zip(*sampling_positions)

    # Integrate the azimuthal part (phi)
    integral_phi, _ = integrate.quad(
        lambda phi: spherical_harmonic(thetas[0], phi, l, m),
        0, 2*np.pi
    )

    # Integrate the polar part (theta)
    integral_theta, _ = integrate.quad(
        lambda theta: integral_phi, 0, np.pi
    )

    return integral_theta

def compute_quadrature_weights(order, sampling_positions):
    # Initialize an array to store the quadrature weights
    weights = []

    # Iterate through (l, m) terms up to the given order
    for l in range(order + 1):
        for m in range(-l, l + 1):
            # Calculate the quadrature weight for the current (l, m) term
            weight = integrate_spherical_harmonics(l, m, sampling_positions)

            # Append the weight to the weights array
            weights.append(weight)

    # Normalize the weights to ensure they sum up to the total surface area
    weights /= np.sum(weights)

    return weights

# Example usage:
# Define the sampling positions in spherical coordinates (azimuth and elevation angles)
## sampling_positions = [(0.0, 0.0), (np.pi/2, 0.0), (np.pi, 0.0), (3*np.pi/2, 0.0)]
sampling_positions = [(np.pi/4,np.pi*3/4),(np.pi*3/4,np.pi*3/4),(np.pi*5/4,np.pi*3/4),(np.pi*7/4,np.pi*3/4),(0,np.pi/4),(np.pi/2,np.pi/4),(np.pi,np.pi/4),(np.pi*3/2,np.pi/4)]
# Set the desired Ambisonic order
order = 2

# Compute the quadrature weights
quadrature_weights = compute_quadrature_weights(order, sampling_positions)

# The 'quadrature_weights' array now contains the computed weights
print(quadrature_weights)