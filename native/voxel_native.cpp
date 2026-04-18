#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <vector>

namespace py = pybind11;

std::vector<std::tuple<int, int, int>> flat_ground_positions(
    int px,
    int pz,
    int radius,
    int ground_y
) {
    std::vector<std::tuple<int, int, int>> out;
    const int side = (radius * 2) + 1;
    out.reserve(side * side);

    for (int dx = -radius; dx <= radius; ++dx) {
        const int x = px + dx;
        for (int dz = -radius; dz <= radius; ++dz) {
            out.emplace_back(x, ground_y, pz + dz);
        }
    }

    return out;
}

std::vector<std::tuple<int, int, int>> filter_custom_positions(
    const std::vector<std::tuple<int, int, int>>& positions,
    int px,
    int py,
    int pz,
    int radius_xy,
    int height
) {
    std::vector<std::tuple<int, int, int>> out;
    out.reserve(positions.size());

    for (const auto& position : positions) {
        const int x = std::get<0>(position);
        const int y = std::get<1>(position);
        const int z = std::get<2>(position);

        if (
            std::abs(x - px) <= radius_xy
            && std::abs(z - pz) <= radius_xy
            && std::abs(y - py) <= height
        ) {
            out.emplace_back(position);
        }
    }

    return out;
}

PYBIND11_MODULE(_voxel_native, m) {
    m.doc() = "Native helpers for PyCraft voxel calculations";

    m.def(
        "flat_ground_positions",
        &flat_ground_positions,
        py::arg("px"),
        py::arg("pz"),
        py::arg("radius"),
        py::arg("ground_y")
    );

    m.def(
        "filter_custom_positions",
        &filter_custom_positions,
        py::arg("positions"),
        py::arg("px"),
        py::arg("py"),
        py::arg("pz"),
        py::arg("radius_xy"),
        py::arg("height")
    );
}
