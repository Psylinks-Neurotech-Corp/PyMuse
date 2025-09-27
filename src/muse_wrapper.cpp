// Enhanced pybind11 wrapper for Interaxon Muse Windows SDK
// Provides discovery, connection, configuration access, and data callbacks for EEG/ACC/GYRO/PPG/OPTICS/BATTERY/DRL.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <optional>
#include <memory>
#include <atomic>
#include <thread>
#include <mutex>
#include <vector>
#include <string>
#include <functional>

// Muse SDK
#include "api/muse_manager_windows.h"
#include "api/bridge_muse.h"
#include "api/bridge_muse_manager.h"
#include "api/bridge_muse_connection_listener.h"
#include "api/bridge_muse_connection_packet.h"
#include "api/bridge_muse_data_listener.h"
#include "api/bridge_muse_data_packet.h"
#include "api/bridge_muse_data_packet_type.h"
#include "api/bridge_muse_preset.h"
#include "api/bridge_muse_configuration.h"
#include "api/bridge_connection_state.h"
#include "api/bridge_muse_model.h"
#include "api/bridge_notch_frequency.h"
#include "api/bridge_optics.h"

namespace py = pybind11;
using namespace interaxon::bridge;

namespace {

struct DeviceInfo {
    std::string name;
    std::string mac;
};

struct MuseConfigurationInfo {
    std::string preset;
    std::string model;
    std::string headband_name;
    std::string microcontroller_id;
    std::string bluetooth_mac;
    std::string serial_number;
    std::string headset_serial_number;
    bool notch_filter_enabled = false;
    std::string notch_filter;
    int32_t eeg_channel_count = 0;
    int32_t output_frequency = 0;
    int32_t downsample_rate = 0;
    int32_t accelerometer_sample_frequency = 0;
    int32_t drl_ref_frequency = 0;
    bool battery_data_enabled = false;
    bool drl_ref_enabled = false;
    int32_t afe_gain = 0;
    int32_t serout_mode = 0;
    int32_t adc_frequency = 0;
    double battery_percent_remaining = 0.0;
};

std::string preset_to_string(MusePreset preset) {
    switch (preset) {
        case MusePreset::PRESET_10: return "10";
        case MusePreset::PRESET_12: return "12";
        case MusePreset::PRESET_14: return "14";
        case MusePreset::PRESET_20: return "20";
        case MusePreset::PRESET_21: return "21";
        case MusePreset::PRESET_1031: return "1031";
        case MusePreset::PRESET_1032: return "1032";
        case MusePreset::PRESET_1033: return "1033";
        case MusePreset::PRESET_1034: return "1034";
        case MusePreset::PRESET_1035: return "1035";
        case MusePreset::PRESET_1036: return "1036";
        default: return "unknown";
    }
}

std::string muse_model_to_string(MuseModel model) {
    switch (model) {
        case MuseModel::MU_01: return "Muse 2014 (MU-01)";
        case MuseModel::MU_02: return "Muse 2016 (MU-02)";
        case MuseModel::MU_03: return "Muse 2 (MU-03)";
        case MuseModel::MU_04: return "Muse S 2019 (MU-04)";
        case MuseModel::MU_05: return "Muse S 2021 (MU-05)";
        case MuseModel::MU_06: return "Muse 2 2024 (MU-06)";
        case MuseModel::MS_03: return "Muse S 2025 (MS-03)";
        default: return "Unknown";
    }
}

std::string notch_frequency_to_string(NotchFrequency freq) {
    switch (freq) {
        case NotchFrequency::NOTCH_50HZ: return "50Hz";
        case NotchFrequency::NOTCH_60HZ: return "60Hz";
        case NotchFrequency::NOTCH_NONE: return "none";
        default: return "unknown";
    }
}

std::string connection_state_to_string(ConnectionState state) {
    switch (state) {
        case ConnectionState::UNKNOWN: return "UNKNOWN";
        case ConnectionState::CONNECTED: return "CONNECTED";
        case ConnectionState::CONNECTING: return "CONNECTING";
        case ConnectionState::DISCONNECTED: return "DISCONNECTED";
        case ConnectionState::NEEDS_UPDATE: return "NEEDS_UPDATE";
        case ConnectionState::NEEDS_LICENSE: return "NEEDS_LICENSE";
        default: return "UNKNOWN";
    }
}

std::string packet_type_to_string(MuseDataPacketType type) {
    switch (type) {
        case MuseDataPacketType::EEG: return "EEG";
        case MuseDataPacketType::ACCELEROMETER: return "ACC";
        case MuseDataPacketType::GYRO: return "GYRO";
        case MuseDataPacketType::PPG: return "PPG";
        case MuseDataPacketType::OPTICS: return "OPTICS";
        case MuseDataPacketType::BATTERY: return "BATTERY";
        case MuseDataPacketType::DRL_REF: return "DRL_REF";
        default: return "";
    }
}

class PyMuseDataListener;
class PyMuseConnectionListener;

class MuseSession {
public:
    MuseSession()
        : manager_(MuseManagerWindows::get_instance()) {}

    std::vector<DeviceInfo> list_devices() {
        std::vector<DeviceInfo> out;
        manager_->start_listening();
        std::this_thread::sleep_for(std::chrono::milliseconds(800));
        auto muses = manager_->get_muses();
        for (auto &m : muses) {
            DeviceInfo di;
            di.name = m->get_name();
            di.mac = m->get_mac_address();
            out.push_back(std::move(di));
        }
        manager_->stop_listening();
        return out;
    }

    void connect_index(int index,
                       py::function on_data,
                       py::function on_state,
                       std::string preset = "auto") {
        if (connected_) {
            throw std::runtime_error("Already connected");
        }
        manager_->start_listening();
        std::this_thread::sleep_for(std::chrono::milliseconds(800));
        auto muses = manager_->get_muses();
        manager_->stop_listening();
        if (index < 0 || index >= static_cast<int>(muses.size())) {
            throw std::runtime_error("Invalid device index");
        }
        muse_ = muses[index];

        connected_ = false;

        auto state_cb = [this](ConnectionState state) {
            if (state == ConnectionState::CONNECTED) {
                connected_ = true;
            } else if (state == ConnectionState::DISCONNECTED || state == ConnectionState::UNKNOWN ||
                       state == ConnectionState::NEEDS_UPDATE || state == ConnectionState::NEEDS_LICENSE) {
                connected_ = false;
            }
        };

        data_listener_ = std::make_shared<PyMuseDataListener>(on_data);
        conn_listener_ = std::make_shared<PyMuseConnectionListener>(on_state, state_cb);

        muse_->register_connection_listener(std::static_pointer_cast<MuseConnectionListener>(conn_listener_));
        muse_->register_data_listener(std::static_pointer_cast<MuseDataListener>(data_listener_), MuseDataPacketType::EEG);
        muse_->register_data_listener(std::static_pointer_cast<MuseDataListener>(data_listener_), MuseDataPacketType::ACCELEROMETER);
        muse_->register_data_listener(std::static_pointer_cast<MuseDataListener>(data_listener_), MuseDataPacketType::GYRO);
        muse_->register_data_listener(std::static_pointer_cast<MuseDataListener>(data_listener_), MuseDataPacketType::PPG);
        muse_->register_data_listener(std::static_pointer_cast<MuseDataListener>(data_listener_), MuseDataPacketType::OPTICS);
        muse_->register_data_listener(std::static_pointer_cast<MuseDataListener>(data_listener_), MuseDataPacketType::BATTERY);
        muse_->register_data_listener(std::static_pointer_cast<MuseDataListener>(data_listener_), MuseDataPacketType::DRL_REF);

        if (preset != "auto") {
            auto p = muse_preset_from_string(preset);
            muse_->set_preset(p);
        }

        muse_->run_asynchronously();
        muse_->enable_data_transmission(true);
    }

    void disconnect() {
        if (!muse_) return;
        connected_ = false;
        try {
            muse_->unregister_all_listeners();
        } catch (...) {}
        muse_->disconnect();
        muse_.reset();
        data_listener_.reset();
        conn_listener_.reset();
    }

    bool is_connected() const { return connected_; }

    std::optional<MuseConfigurationInfo> get_configuration() {
        if (!muse_) {
            return std::nullopt;
        }
        try {
            auto cfg = muse_->get_muse_configuration();
            if (!cfg) {
                return std::nullopt;
            }
            MuseConfigurationInfo info;
            info.preset = preset_to_string(cfg->get_preset());
            info.model = muse_model_to_string(cfg->get_model());
            info.headband_name = cfg->get_headband_name();
            info.microcontroller_id = cfg->get_microcontroller_id();
            info.bluetooth_mac = cfg->get_bluetooth_mac();
            info.serial_number = cfg->get_serial_number();
            info.headset_serial_number = cfg->get_headset_serial_number();
            info.notch_filter_enabled = cfg->get_notch_filter_enabled();
            info.notch_filter = notch_frequency_to_string(cfg->get_notch_filter());
            info.eeg_channel_count = cfg->get_eeg_channel_count();
            info.output_frequency = cfg->get_output_frequency();
            info.downsample_rate = cfg->get_downsample_rate();
            info.accelerometer_sample_frequency = cfg->get_accelerometer_sample_frequency();
            info.drl_ref_frequency = cfg->get_drl_ref_frequency();
            info.battery_data_enabled = cfg->get_battery_data_enabled();
            info.drl_ref_enabled = cfg->get_drl_ref_enabled();
            info.afe_gain = cfg->get_afe_gain();
            info.serout_mode = cfg->get_serout_mode();
            info.adc_frequency = cfg->get_adc_frequency();
            info.battery_percent_remaining = cfg->get_battery_percent_remaining();
            return info;
        } catch (...) {
            return std::nullopt;
        }
    }

    static MusePreset muse_preset_from_string(const std::string &s) {
        if (s == "1031") return MusePreset::PRESET_1031;
        if (s == "1032") return MusePreset::PRESET_1032;
        if (s == "1033") return MusePreset::PRESET_1033;
        if (s == "1034") return MusePreset::PRESET_1034;
        if (s == "1035") return MusePreset::PRESET_1035;
        if (s == "1036") return MusePreset::PRESET_1036;
        if (s == "20") return MusePreset::PRESET_20;
        if (s == "21") return MusePreset::PRESET_21;
        if (s == "10") return MusePreset::PRESET_10;
        if (s == "12") return MusePreset::PRESET_12;
        if (s == "14") return MusePreset::PRESET_14;
        return MusePreset::PRESET_21;
    }

private:
    std::shared_ptr<MuseManagerWindows> manager_;
    std::shared_ptr<Muse> muse_;
    std::shared_ptr<PyMuseDataListener> data_listener_;
    std::shared_ptr<PyMuseConnectionListener> conn_listener_;
    std::atomic<bool> connected_{false};
};

class PyMuseDataListener : public MuseDataListener {
public:
    explicit PyMuseDataListener(py::function cb) : cb_(std::move(cb)) {}

    void receive_muse_data_packet(const std::shared_ptr<MuseDataPacket> & packet,
                                  const std::shared_ptr<Muse> & muse) override {
        try {
            py::gil_scoped_acquire gil;
            auto type = packet->packet_type();
            auto ts = packet->timestamp();
            std::vector<double> vals = packet->values();
            std::string type_str = packet_type_to_string(type);
            if (type_str.empty()) {
                return;
            }
            cb_(type_str, ts, vals);
        } catch (...) {}
    }

    void receive_muse_artifact_packet(const MuseArtifactPacket &, const std::shared_ptr<Muse> &) override {
        // Not used in this wrapper version
    }
private:
    py::function cb_;
};

class PyMuseConnectionListener : public MuseConnectionListener {
public:
    PyMuseConnectionListener(py::function cb, std::function<void(ConnectionState)> state_cb)
        : cb_(std::move(cb)), state_cb_(std::move(state_cb)) {}

    void receive_muse_connection_packet(const MuseConnectionPacket & packet,
                                        const std::shared_ptr<Muse> & muse) override {
        try {
            py::gil_scoped_acquire gil;
            auto prev = connection_state_to_string(packet.previous_connection_state);
            auto curr = connection_state_to_string(packet.current_connection_state);
            cb_(prev + "->" + curr);
        } catch (...) {}
        try {
            state_cb_(packet.current_connection_state);
        } catch (...) {}
    }
private:
    py::function cb_;
    std::function<void(ConnectionState)> state_cb_;
};

} // namespace

PYBIND11_MODULE(muse_wrapper, m) {
    m.doc() = "Python bindings for Interaxon Muse Windows SDK (extended)";

    py::class_<DeviceInfo>(m, "DeviceInfo")
        .def_readonly("name", &DeviceInfo::name)
        .def_readonly("mac", &DeviceInfo::mac);

    py::class_<MuseConfigurationInfo>(m, "MuseConfigurationInfo")
        .def_readonly("preset", &MuseConfigurationInfo::preset)
        .def_readonly("model", &MuseConfigurationInfo::model)
        .def_readonly("headband_name", &MuseConfigurationInfo::headband_name)
        .def_readonly("microcontroller_id", &MuseConfigurationInfo::microcontroller_id)
        .def_readonly("bluetooth_mac", &MuseConfigurationInfo::bluetooth_mac)
        .def_readonly("serial_number", &MuseConfigurationInfo::serial_number)
        .def_readonly("headset_serial_number", &MuseConfigurationInfo::headset_serial_number)
        .def_readonly("notch_filter_enabled", &MuseConfigurationInfo::notch_filter_enabled)
        .def_readonly("notch_filter", &MuseConfigurationInfo::notch_filter)
        .def_readonly("eeg_channel_count", &MuseConfigurationInfo::eeg_channel_count)
        .def_readonly("output_frequency", &MuseConfigurationInfo::output_frequency)
        .def_readonly("downsample_rate", &MuseConfigurationInfo::downsample_rate)
        .def_readonly("accelerometer_sample_frequency", &MuseConfigurationInfo::accelerometer_sample_frequency)
        .def_readonly("drl_ref_frequency", &MuseConfigurationInfo::drl_ref_frequency)
        .def_readonly("battery_data_enabled", &MuseConfigurationInfo::battery_data_enabled)
        .def_readonly("drl_ref_enabled", &MuseConfigurationInfo::drl_ref_enabled)
        .def_readonly("afe_gain", &MuseConfigurationInfo::afe_gain)
        .def_readonly("serout_mode", &MuseConfigurationInfo::serout_mode)
        .def_readonly("adc_frequency", &MuseConfigurationInfo::adc_frequency)
        .def_readonly("battery_percent_remaining", &MuseConfigurationInfo::battery_percent_remaining);

    py::class_<MuseSession>(m, "MuseSession")
        .def(py::init<>())
        .def("list_devices", &MuseSession::list_devices, "Scan and list available Muse devices")
        .def("connect_index", &MuseSession::connect_index,
             py::arg("index"), py::arg("on_data"), py::arg("on_state"), py::arg("preset") = "auto",
             "Connect to device by index. on_data(type:str, ts:int, values:list[float])")
        .def("disconnect", &MuseSession::disconnect)
        .def("is_connected", &MuseSession::is_connected)
        .def("get_configuration", &MuseSession::get_configuration,
             "Return the latest MuseConfigurationInfo captured from the device, if available");
}
