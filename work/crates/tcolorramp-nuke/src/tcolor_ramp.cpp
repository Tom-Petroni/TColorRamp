static const char* const CLASS = "TColorRamp";
static const char* const HELP =
    "Remaps each pixel's luminance through a custom color ramp.\n"
    "The luma (Rec.709) of the input is used as the ramp coordinate.\n"
    "Alpha is passed through unchanged.";

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "DDImage/Iop.h"
#include "DDImage/Knob.h"
#include "DDImage/Knobs.h"
#include "DDImage/Row.h"
#include "DDImage/TableKnobI.h"

using namespace DD::Image;

namespace {
const char* const kInterpolationModes[] = {
    "linear",
    "constant",
    "smooth",
    "smoother",
    nullptr,
};

const char* const kSourceModes[] = {
    "luma",
    "red",
    "green",
    "blue",
    "alpha",
    nullptr,
};

const char* const kValueRangeModes[] = {
    "unit",
    "image",
    nullptr,
};

const char* const kBlendModes[] = {
    "normal",
    "multiply",
    "screen",
    "overlay",
    "softlight",
    nullptr,
};

const char* const kWrapModes[] = {
    "clamp",
    "repeat",
    "pingpong",
    nullptr,
};
}

class TColorRamp : public Iop {

  // ── color ramp state ──────────────────────────────────────────────────────

  struct ColorRampStop {
    float pos = 0.0f;
    float r   = 0.0f;
    float g   = 0.0f;
    float b   = 0.0f;
  };

  std::string         color_ramp_serialized_ = "0|0|0|0;1|1|1|1";
  Table_KnobI*        color_ramp_table_      = nullptr;
  std::vector<ColorRampStop> color_ramp_stops_;
  int color_ramp_selected_index_ = 0;
  double color_ramp_selected_pos_ = 0.0;
  double color_ramp_selected_color_[3] = {0.0, 0.0, 0.0};
  int color_ramp_source_ = 0;
  int color_ramp_value_range_mode_ = 0;
  int color_ramp_interpolation_ = 0;
  double color_ramp_mix_ = 1.0;
  int color_ramp_blend_mode_ = 0;
  double phase_z_ = 0.0;
  double phase_zspeed_ = 0.0;
  int phase_wrap_mode_ = 1;
  bool syncing_selected_knobs_ = false;
  float source_value_min_ = 0.0f;
  float source_value_max_ = 1.0f;
  float source_value_inv_span_ = 1.0f;

  static constexpr int kLutSize = 1024;
  float lut_r_[kLutSize] = {};
  float lut_g_[kLutSize] = {};
  float lut_b_[kLutSize] = {};
  float phase_lut_r_[kLutSize] = {};
  float phase_lut_g_[kLutSize] = {};
  float phase_lut_b_[kLutSize] = {};
  std::atomic<bool> lut_ready_{false};

  // ── utilities ─────────────────────────────────────────────────────────────

  static float clamp01(float v) {
    return std::max(0.0f, std::min(1.0f, v));
  }

  static float wrap01(float v) {
    float f = std::fmod(v, 1.0f);
    if (f < 0.0f) {
      f += 1.0f;
    }
    return f;
  }

  static float pingpong01(float v) {
    float f = std::fmod(v, 2.0f);
    if (f < 0.0f) {
      f += 2.0f;
    }
    return (f <= 1.0f) ? f : (2.0f - f);
  }

  static float apply_phase_coord(float v,
                                 float phase,
                                 int wrap_mode,
                                 bool repeat_shift) {
    const float base = clamp01(v);
    const float shifted = base + phase;
    switch (wrap_mode) {
      case 0:  // clamp
        return clamp01(shifted);
      case 2:  // pingpong
        return pingpong01(shifted);
      case 1:  // repeat
      default:
        if (!repeat_shift) {
          return base;
        }
        return wrap01(shifted);
    }
  }

  static float blend_channel(float base, float tint, int mode) {
    const float b = clamp01(base);
    const float t = clamp01(tint);
    switch (mode) {
      case 1:  // multiply
        return b * t;
      case 2:  // screen
        return 1.0f - (1.0f - b) * (1.0f - t);
      case 3:  // overlay
        return (b < 0.5f) ? (2.0f * b * t)
                          : (1.0f - 2.0f * (1.0f - b) * (1.0f - t));
      case 4: {  // softlight
        const float g = (b <= 0.25f)
                            ? (((16.0f * b - 12.0f) * b + 4.0f) * b)
                            : std::sqrt(b);
        return (t < 0.5f)
                   ? (b - (1.0f - 2.0f * t) * b * (1.0f - b))
                   : (b + (2.0f * t - 1.0f) * (g - b));
      }
      default:  // normal
        return t;
    }
  }

  float source_value_from_channels(float r, float g, float b, float a) const {
    switch (color_ramp_source_) {
      case 1:  // red
        return r;
      case 2:  // green
        return g;
      case 3:  // blue
        return b;
      case 4:  // alpha
        return a;
      case 0:  // luma
      default:
        return r * 0.2126f + g * 0.7152f + b * 0.0722f;
    }
  }

  float normalize_source_value(float raw) const {
    if (color_ramp_value_range_mode_ == 1) {
      return (raw - source_value_min_) * source_value_inv_span_;
    }
    return raw;
  }

  static unsigned pack_rgb8(float r, float g, float b) {
    const unsigned r8 = static_cast<unsigned>(std::round(clamp01(r) * 255.0f));
    const unsigned g8 = static_cast<unsigned>(std::round(clamp01(g) * 255.0f));
    const unsigned b8 = static_cast<unsigned>(std::round(clamp01(b) * 255.0f));
    return (r8 << 16) | (g8 << 8) | b8;
  }

  static ColorRampStop unpack_stop(float pos, unsigned packed_rgb) {
    ColorRampStop s;
    s.pos = clamp01(pos);
    s.r   = static_cast<float>((packed_rgb >> 16) & 0xFFu) / 255.0f;
    s.g   = static_cast<float>((packed_rgb >>  8) & 0xFFu) / 255.0f;
    s.b   = static_cast<float>( packed_rgb        & 0xFFu) / 255.0f;
    return s;
  }

  static std::string trim_ascii_copy(const std::string& s) {
    size_t begin = 0;
    while (begin < s.size() &&
           std::isspace(static_cast<unsigned char>(s[begin])) != 0) {
      ++begin;
    }
    size_t end = s.size();
    while (end > begin &&
           std::isspace(static_cast<unsigned char>(s[end - 1])) != 0) {
      --end;
    }
    return s.substr(begin, end - begin);
  }

  static std::string serialize_stops(const std::vector<ColorRampStop>& stops) {
    if (stops.empty()) {
      return "0|0|0|0;1|1|1|1";
    }
    std::string out;
    out.reserve(stops.size() * 40);
    char buf[64];
    for (size_t i = 0; i < stops.size(); ++i) {
      const ColorRampStop& s = stops[i];
      if (i > 0) {
        out += ';';
      }
      std::snprintf(buf, sizeof(buf), "%.6f|%.6f|%.6f|%.6f",
                    static_cast<double>(clamp01(s.pos)),
                    static_cast<double>(clamp01(s.r)),
                    static_cast<double>(clamp01(s.g)),
                    static_cast<double>(clamp01(s.b)));
      out += buf;
    }
    return out;
  }

  static bool parse_serialized_stop(const std::string& token,
                                    ColorRampStop* out_stop) {
    if (!out_stop) {
      return false;
    }
    float pos = 0.0f, r = 0.0f, g = 0.0f, b = 0.0f;
    if (std::sscanf(token.c_str(), " %f | %f | %f | %f ",
                    &pos, &r, &g, &b) != 4) {
      return false;
    }
    out_stop->pos = clamp01(pos);
    out_stop->r   = clamp01(r);
    out_stop->g   = clamp01(g);
    out_stop->b   = clamp01(b);
    return true;
  }

  // ── table defaults ────────────────────────────────────────────────────────

  void ensure_color_ramp_table_defaults() {
    if (!color_ramp_table_) {
      return;
    }
    if (color_ramp_table_->getColumnCount() == 0) {
      color_ramp_table_->addColumn(
          "pos", "Pos", Table_KnobI::FloatColumn, true, 70, true);
      color_ramp_table_->addColumn(
          "color", "Color", Table_KnobI::ColorPickerColumn, true, 140, true);
      color_ramp_table_->setEditingWidgetFlags(
          Table_KnobI::AddRowWidget | Table_KnobI::DeleteRowsWidget);
#if defined(kDDImageVersionMajorNum) && (kDDImageVersionMajorNum >= 16)
      color_ramp_table_->setFixedHeight(120);
#endif
    }
    if (color_ramp_table_->getRowCount() == 0) {
      const int row0    = color_ramp_table_->addRow();
      const int row1    = color_ramp_table_->addRow();
      const int pos_col = color_ramp_table_->getColumnIndex("pos");
      const int col_col = color_ramp_table_->getColumnIndex("color");
      if (pos_col >= 0 && col_col >= 0) {
        color_ramp_table_->setCellFloat(row0, pos_col, 0.0f);
        color_ramp_table_->setCellColor(row0, col_col, pack_rgb8(0.0f, 0.0f, 0.0f));
        color_ramp_table_->setCellFloat(row1, pos_col, 1.0f);
        color_ramp_table_->setCellColor(row1, col_col, pack_rgb8(1.0f, 1.0f, 1.0f));
      }
    }
  }

  // ── serialization / sync ──────────────────────────────────────────────────

  bool sync_color_ramp_stops_from_serialized() {
    color_ramp_stops_.clear();
    if (color_ramp_serialized_.empty()) {
      return false;
    }

    std::vector<ColorRampStop> parsed;
    parsed.reserve(8);

    size_t cursor = 0;
    while (cursor <= color_ramp_serialized_.size()) {
      size_t sep = color_ramp_serialized_.find(';', cursor);
      if (sep == std::string::npos) {
        sep = color_ramp_serialized_.size();
      }
      const std::string token =
          trim_ascii_copy(color_ramp_serialized_.substr(cursor, sep - cursor));
      if (!token.empty()) {
        ColorRampStop stop;
        if (parse_serialized_stop(token, &stop)) {
          parsed.push_back(stop);
        }
      }
      if (sep == color_ramp_serialized_.size()) {
        break;
      }
      cursor = sep + 1;
    }

    if (parsed.empty()) {
      return false;
    }
    std::sort(parsed.begin(), parsed.end(),
              [](const ColorRampStop& a, const ColorRampStop& b) {
                return a.pos < b.pos;
              });
    color_ramp_stops_ = parsed;
    return true;
  }

  bool sync_color_ramp_stops_from_table() {
    color_ramp_stops_.clear();
    if (!color_ramp_table_) {
      return false;
    }
    ensure_color_ramp_table_defaults();

    const int row_count = color_ramp_table_->getRowCount();
    const int pos_col   = color_ramp_table_->getColumnIndex("pos");
    const int col_col   = color_ramp_table_->getColumnIndex("color");
    if (row_count <= 0 || pos_col < 0 || col_col < 0) {
      return false;
    }

    color_ramp_stops_.reserve(static_cast<size_t>(row_count));
    for (int row = 0; row < row_count; ++row) {
      const float    pos        = color_ramp_table_->getCellFloat(row, pos_col);
      const unsigned packed_rgb = color_ramp_table_->getCellColor(row, col_col);
      color_ramp_stops_.push_back(unpack_stop(pos, packed_rgb));
    }

    if (color_ramp_stops_.empty()) {
      return false;
    }
    std::sort(color_ramp_stops_.begin(), color_ramp_stops_.end(),
              [](const ColorRampStop& a, const ColorRampStop& b) {
                return a.pos < b.pos;
              });
    return true;
  }

  void sync_color_ramp_serialized_from_stops() {
    color_ramp_serialized_ = serialize_stops(color_ramp_stops_);
  }

  bool sync_color_ramp_stops() {
    if (sync_color_ramp_stops_from_serialized()) {
      return true;
    }
    if (sync_color_ramp_stops_from_table()) {
      sync_color_ramp_serialized_from_stops();
      return true;
    }
    return false;
  }

  int clamped_selected_index() const {
    if (color_ramp_stops_.empty()) {
      return 0;
    }
    const int last = static_cast<int>(color_ramp_stops_.size()) - 1;
    return std::max(0, std::min(color_ramp_selected_index_, last));
  }

  void sync_selected_knobs_from_stops() {
    if (color_ramp_stops_.empty()) {
      color_ramp_selected_index_ = 0;
      color_ramp_selected_pos_ = 0.0;
      color_ramp_selected_color_[0] = 0.0;
      color_ramp_selected_color_[1] = 0.0;
      color_ramp_selected_color_[2] = 0.0;
      return;
    }

    color_ramp_selected_index_ = clamped_selected_index();
    const ColorRampStop& stop = color_ramp_stops_[static_cast<size_t>(color_ramp_selected_index_)];
    color_ramp_selected_pos_ = static_cast<double>(clamp01(stop.pos));
    color_ramp_selected_color_[0] = static_cast<double>(clamp01(stop.r));
    color_ramp_selected_color_[1] = static_cast<double>(clamp01(stop.g));
    color_ramp_selected_color_[2] = static_cast<double>(clamp01(stop.b));
  }

  void sync_selected_knobs_to_ui() {
    syncing_selected_knobs_ = true;

    if (Knob* k = knob("color_ramp_selected_index")) {
      char buf[32];
      std::snprintf(buf, sizeof(buf), "%d", color_ramp_selected_index_);
      k->set_text(buf);
    }
    if (Knob* k = knob("color_ramp_pos")) {
      char buf[64];
      std::snprintf(buf, sizeof(buf), "%.6f", color_ramp_selected_pos_);
      k->set_text(buf);
    }
    if (Knob* k = knob("color_ramp_color")) {
      char buf[128];
      std::snprintf(
          buf,
          sizeof(buf),
          "%.6f %.6f %.6f",
          color_ramp_selected_color_[0],
          color_ramp_selected_color_[1],
          color_ramp_selected_color_[2]);
      k->set_text(buf);
    }

    syncing_selected_knobs_ = false;
  }

  void apply_selected_knobs_to_stops() {
    if (color_ramp_stops_.empty()) {
      return;
    }

    color_ramp_selected_index_ = clamped_selected_index();
    ColorRampStop updated = color_ramp_stops_[static_cast<size_t>(color_ramp_selected_index_)];
    updated.pos = clamp01(static_cast<float>(color_ramp_selected_pos_));
    updated.r = clamp01(static_cast<float>(color_ramp_selected_color_[0]));
    updated.g = clamp01(static_cast<float>(color_ramp_selected_color_[1]));
    updated.b = clamp01(static_cast<float>(color_ramp_selected_color_[2]));
    color_ramp_stops_[static_cast<size_t>(color_ramp_selected_index_)] = updated;

    std::sort(color_ramp_stops_.begin(), color_ramp_stops_.end(),
              [](const ColorRampStop& a, const ColorRampStop& b) {
                return a.pos < b.pos;
              });

    int best_index = 0;
    float best_score = 1e9f;
    for (size_t i = 0; i < color_ramp_stops_.size(); ++i) {
      const ColorRampStop& s = color_ramp_stops_[i];
      const float score =
          std::fabs(s.pos - updated.pos) +
          0.01f * (std::fabs(s.r - updated.r) +
                   std::fabs(s.g - updated.g) +
                   std::fabs(s.b - updated.b));
      if (score < best_score) {
        best_score = score;
        best_index = static_cast<int>(i);
      }
    }
    color_ramp_selected_index_ = best_index;
    sync_selected_knobs_from_stops();
  }

  // ── LUT ───────────────────────────────────────────────────────────────────

  struct RGB { float r, g, b; };

  RGB sample_lut_rgb(const float* lr,
                     const float* lg,
                     const float* lb,
                     float t) const {
    const float u  = clamp01(t) * static_cast<float>(kLutSize - 1);
    const int   i0 = static_cast<int>(u);
    const int   i1 = std::min(i0 + 1, kLutSize - 1);
    const float f  = u - static_cast<float>(i0);
    return {
        lr[i0] + (lr[i1] - lr[i0]) * f,
        lg[i0] + (lg[i1] - lg[i0]) * f,
        lb[i0] + (lb[i1] - lb[i0]) * f,
    };
  }

  void rebuild_color_ramp_lut() {
    if (color_ramp_stops_.empty()) {
      lut_ready_.store(false, std::memory_order_release);
      return;
    }

    auto sample_from_stops = [this](float x) -> RGB {
      const ColorRampStop* left  = &color_ramp_stops_.front();
      const ColorRampStop* right = &color_ramp_stops_.back();
      for (size_t s = 1; s < color_ramp_stops_.size(); ++s) {
        if (x <= color_ramp_stops_[s].pos) {
          left  = &color_ramp_stops_[s - 1];
          right = &color_ramp_stops_[s];
          break;
        }
      }

      float t = 0.0f;
      const float span = right->pos - left->pos;
      if (span > 1e-6f) {
        t = clamp01((x - left->pos) / span);
      } else {
        t = (x >= right->pos) ? 1.0f : 0.0f;
      }

      switch (color_ramp_interpolation_) {
        case 1:  // constant
          t = (x < right->pos) ? 0.0f : 1.0f;
          break;
        case 2:  // smoothstep
          t = t * t * (3.0f - 2.0f * t);
          break;
        case 3:  // smootherstep
          t = t * t * t * (t * (t * 6.0f - 15.0f) + 10.0f);
          break;
        default:  // linear
          break;
      }

      return {
          left->r + (right->r - left->r) * t,
          left->g + (right->g - left->g) * t,
          left->b + (right->b - left->b) * t,
      };
    };

    for (int i = 0; i < kLutSize; ++i) {
      const float x = static_cast<float>(i) / static_cast<float>(kLutSize - 1);
      const RGB c = sample_from_stops(x);
      lut_r_[i] = c.r;
      lut_g_[i] = c.g;
      lut_b_[i] = c.b;
    }

    float seam_width = 0.0f;
    if (color_ramp_stops_.size() >= 2) {
      const size_t n = color_ramp_stops_.size();
      const float first_span =
          std::max(0.0f, color_ramp_stops_[1].pos - color_ramp_stops_[0].pos);
      const float last_span =
          std::max(0.0f, color_ramp_stops_[n - 1].pos - color_ramp_stops_[n - 2].pos);
      seam_width = 0.5f * std::min(first_span, last_span);
      seam_width = std::max(0.0f, std::min(0.5f, seam_width));
      const float min_w = 1.0f / static_cast<float>(kLutSize);
      if (seam_width < min_w) {
        seam_width = 0.0f;
      }
    }

    if (seam_width <= 0.0f) {
      std::memcpy(phase_lut_r_, lut_r_, sizeof(lut_r_));
      std::memcpy(phase_lut_g_, lut_g_, sizeof(lut_g_));
      std::memcpy(phase_lut_b_, lut_b_, sizeof(lut_b_));
    } else {
      const float seam_min = seam_width;
      const float seam_max = 1.0f - seam_width;
      for (int i = 0; i < kLutSize; ++i) {
        const float x = static_cast<float>(i) / static_cast<float>(kLutSize - 1);
        if (x < seam_min || x > seam_max) {
          const float p = (x < seam_min) ? x : (x - 1.0f);
          const float s = clamp01((p + seam_width) / (2.0f * seam_width));
          const float x_end = (1.0f - seam_width) + s * seam_width;
          const float x_start = s * seam_width;
          const RGB c_end = sample_lut_rgb(lut_r_, lut_g_, lut_b_, x_end);
          const RGB c_start = sample_lut_rgb(lut_r_, lut_g_, lut_b_, x_start);
          phase_lut_r_[i] = c_end.r + (c_start.r - c_end.r) * s;
          phase_lut_g_[i] = c_end.g + (c_start.g - c_end.g) * s;
          phase_lut_b_[i] = c_end.b + (c_start.b - c_end.b) * s;
        } else {
          phase_lut_r_[i] = lut_r_[i];
          phase_lut_g_[i] = lut_g_[i];
          phase_lut_b_[i] = lut_b_[i];
        }
      }
    }

    lut_ready_.store(true, std::memory_order_release);
  }

  RGB sample_color_ramp(float t, bool phase_mode) const {
    if (!lut_ready_.load(std::memory_order_acquire)) {
      const float g = clamp01(t);
      return {g, g, g};
    }
    if (phase_mode) {
      return sample_lut_rgb(phase_lut_r_, phase_lut_g_, phase_lut_b_, t);
    }
    return sample_lut_rgb(lut_r_, lut_g_, lut_b_, t);
  }

  float animated_phase_offset() const {
    const float frame = static_cast<float>(outputContext().frame());
    const float z_anim = static_cast<float>(phase_zspeed_ * 0.01) * frame;
    return static_cast<float>(phase_z_) + z_anim;
  }

 public:
  explicit TColorRamp(Node* node) : Iop(node) {}

  int minimum_inputs() const override { return 1; }
  int maximum_inputs() const override { return 2; }
  int optional_input() const override { return 1; }

  const char* input_label(int input, char* buffer) const override {
    (void)buffer;
    if (input == 0) {
      return "src";
    }
    if (input == 1) {
      return "mask";
    }
    return "";
  }

  std::string input_longlabel(int input) const override {
    if (input == 0) {
      return "Source";
    }
    if (input == 1) {
      return "Mask (optional)";
    }
    return "";
  }

  // ── Iop interface ─────────────────────────────────────────────────────────

  void _validate(bool for_real) override {
    copy_info();
    lut_ready_.store(false, std::memory_order_release);
    source_value_min_ = 0.0f;
    source_value_max_ = 1.0f;
    source_value_inv_span_ = 1.0f;
    if (for_real) {
      sync_color_ramp_stops();
      rebuild_color_ramp_lut();
    }
  }

  void _open() override {
    Iop::_open();

    source_value_min_ = 0.0f;
    source_value_max_ = 1.0f;
    source_value_inv_span_ = 1.0f;

    if (color_ramp_value_range_mode_ != 1) {
      return;
    }

    const Box src_box = input0().info();
    const int x0 = src_box.x();
    const int x1 = src_box.r();
    const int y0 = src_box.y();
    const int y1 = src_box.t();
    if (x1 <= x0 || y1 <= y0) {
      return;
    }

    ChannelSet src_needed;
    switch (color_ramp_source_) {
      case 1:
        src_needed += Chan_Red;
        break;
      case 2:
        src_needed += Chan_Green;
        break;
      case 3:
        src_needed += Chan_Blue;
        break;
      case 4:
        src_needed += Chan_Alpha;
        break;
      case 0:
      default:
        src_needed += Mask_RGB;
        break;
    }

    Row src_row(x0, x1);
    bool first = true;
    float min_v = 0.0f;
    float max_v = 1.0f;
    const bool src_has_alpha = input0().channels().contains(Chan_Alpha);

    for (int y = y0; y < y1; ++y) {
      src_row.get(input0(), y, x0, x1, src_needed);
      const float* inR = src_row[Chan_Red];
      const float* inG = src_row[Chan_Green];
      const float* inB = src_row[Chan_Blue];
      const float* inA = src_row[Chan_Alpha];
      for (int x = x0; x < x1; ++x) {
        const float r = inR ? inR[x] : 0.0f;
        const float g = inG ? inG[x] : 0.0f;
        const float b = inB ? inB[x] : 0.0f;
        const float a = (src_has_alpha && inA) ? inA[x] : 1.0f;
        const float v = source_value_from_channels(r, g, b, a);
        if (first) {
          min_v = v;
          max_v = v;
          first = false;
        } else {
          if (v < min_v) {
            min_v = v;
          }
          if (v > max_v) {
            max_v = v;
          }
        }
      }
    }

    if (first) {
      return;
    }

    const float span = max_v - min_v;
    source_value_min_ = min_v;
    source_value_max_ = max_v;
    source_value_inv_span_ = (std::fabs(span) > 1e-8f) ? (1.0f / span) : 1.0f;
  }

  void _request(int x, int y, int r, int t,
                ChannelMask channels, int count) override {
    ChannelSet needed(channels);
    needed += Mask_RGB;
    needed += Chan_Alpha;
    if (color_ramp_value_range_mode_ == 1) {
      const Box src_box = input0().info();
      input0().request(src_box.x(), src_box.y(), src_box.r(), src_box.t(), needed, count);
    } else {
      input0().request(x, y, r, t, needed, count);
    }

    Iop* mask_iop = input(1);
    if (mask_iop && !mask_iop->isBlackIop()) {
      ChannelSet mask_needed;
      mask_needed += Chan_Red;
      mask_needed += Chan_Alpha;
      mask_iop->request(x, y, r, t, mask_needed, count);
    }
  }

  void engine(int y, int x, int r,
              ChannelMask channels, Row& row) override {
    ChannelSet needed(channels);
    needed += Mask_RGB;
    needed += Chan_Alpha;
    row.get(input0(), y, x, r, needed);

    if (!(channels & Mask_RGB)) {
      return;
    }

    const float* inR = row[Chan_Red];
    const float* inG = row[Chan_Green];
    const float* inB = row[Chan_Blue];
    const float* inA = row[Chan_Alpha];
    float* outR = row.writable(Chan_Red);
    float* outG = row.writable(Chan_Green);
    float* outB = row.writable(Chan_Blue);
    const bool src_has_alpha = input0().channels().contains(Chan_Alpha);

    Row mask_row(x, r);
    const float* mask_r = nullptr;
    const float* mask_a = nullptr;
    Iop* mask_iop = input(1);
    bool has_mask = false;
    if (mask_iop && !mask_iop->isBlackIop()) {
      ChannelSet mask_needed;
      mask_needed += Chan_Red;
      mask_needed += Chan_Alpha;
      mask_row.get(*mask_iop, y, x, r, mask_needed);
      has_mask = true;
      if (mask_iop->channels().contains(Chan_Alpha)) {
        mask_a = mask_row[Chan_Alpha];
      }
      if (mask_iop->channels().contains(Chan_Red)) {
        mask_r = mask_row[Chan_Red];
      }
    }

    const float phase = animated_phase_offset();
    const bool repeat_shift = (phase_wrap_mode_ == 1) &&
                              (wrap01(phase) > 1e-8f);
    const bool use_phase_lut = repeat_shift;
    const float global_mix = clamp01(static_cast<float>(color_ramp_mix_));

    for (int col = x; col < r; ++col) {
      const float src_a = (src_has_alpha && inA) ? inA[col] : 1.0f;
      const float ramp_in_raw = source_value_from_channels(
          inR[col], inG[col], inB[col], src_a);
      const float ramp_in = normalize_source_value(ramp_in_raw);
      const float ramp_coord =
          apply_phase_coord(ramp_in, phase, phase_wrap_mode_, repeat_shift);
      const RGB mapped = sample_color_ramp(ramp_coord, use_phase_lut);

      float m = 1.0f;
      if (has_mask) {
        if (mask_a) {
          m = mask_a[col];
        } else if (mask_r) {
          m = mask_r[col];
        } else {
          m = 0.0f;
        }
        m = clamp01(m);
      }

      const float amount = clamp01(m * global_mix);
      const float blended_r = blend_channel(inR[col], mapped.r, color_ramp_blend_mode_);
      const float blended_g = blend_channel(inG[col], mapped.g, color_ramp_blend_mode_);
      const float blended_b = blend_channel(inB[col], mapped.b, color_ramp_blend_mode_);

      outR[col] = inR[col] + (blended_r - inR[col]) * amount;
      outG[col] = inG[col] + (blended_g - inG[col]) * amount;
      outB[col] = inB[col] + (blended_b - inB[col]) * amount;
    }
  }

  // ── knobs ─────────────────────────────────────────────────────────────────

  void knobs(Knob_Callback f) override {
    Knob* stops_knob = Table_knob(f, "color_ramp_stops", "stops");
    Tooltip(f, "Internal compatibility table storage for color ramp stops.");
    SetFlags(f, Knob::INVISIBLE);

    String_knob(f, &color_ramp_serialized_, "color_ramp_serialized", "");
    SetFlags(f, Knob::INVISIBLE);

    Python_knob(
        f,
        "__import__('TColorRamp._python_color_ramp', fromlist=['*']).TColorRampInlineKnob()",
        "color_ramp_inline",
        "");
    SetFlags(f, Knob::STARTLINE);
    Tooltip(f, "Blender-like inline color ramp editor.");

    Double_knob(f, &color_ramp_selected_pos_, "color_ramp_pos", "position");
    SetRange(f, 0.0, 1.0);
    SetFlags(f, Knob::SLIDER);
    Tooltip(f, "Selected color stop position (0..1).");

    if (Knob* divider = Divider(f)) {
      divider->name("color_ramp_divider_pos");
      divider->label("");
    }

    Color_knob(f, color_ramp_selected_color_, "color_ramp_color", "color");
    Tooltip(f, "Selected color stop value.");

    if (Knob* divider = Divider(f)) {
      divider->name("color_ramp_divider_color");
      divider->label("");
    }

    Enumeration_knob(
        f,
        &color_ramp_interpolation_,
        kInterpolationModes,
        "color_ramp_interpolation",
        "interpolation");
    Tooltip(f, "Interpolation mode between color stops.");

    if (Knob* divider = Divider(f)) {
      divider->name("color_ramp_divider_interp");
      divider->label("");
    }

    Enumeration_knob(
        f,
        &color_ramp_source_,
        kSourceModes,
        "color_ramp_source",
        "source");
    Tooltip(f, "Ramp lookup source channel.");

    Enumeration_knob(
        f,
        &color_ramp_value_range_mode_,
        kValueRangeModes,
        "color_ramp_value_range",
        "range");
    ClearFlags(f, Knob::STARTLINE);
    Tooltip(f, "Value range mapping. 'unit' uses 0..1, 'image' remaps min/max of source.");

    Enumeration_knob(
        f,
        &color_ramp_blend_mode_,
        kBlendModes,
        "color_ramp_blend_mode",
        "blend mode");
    Tooltip(f, "Blend mode used to combine source with ramp color.");

    Int_knob(f, &color_ramp_selected_index_, "color_ramp_selected_index", "");
    SetFlags(f, Knob::INVISIBLE);

    if (Knob* divider = Divider(f)) {
      divider->name("color_ramp_divider_source_blend");
      divider->label("");
    }

    Python_knob(
        f,
        "__import__('TColorRamp._python_color_ramp', fromlist=['*']).TColorRampPresetKnob()",
        "color_ramp_presets",
        "");
    SetFlags(f, Knob::STARTLINE);
    Tooltip(f, "Preset controls.");

    if (Knob* divider = Divider(f)) {
      divider->name("color_ramp_divider_presets");
      divider->label("");
    }

    Double_knob(f, &phase_z_, "color_ramp_z", "z");
    Tooltip(f, "Phase offset applied to ramp coordinate.");

    Double_knob(f, &phase_zspeed_, "color_ramp_zspeed", "z speed");
    Tooltip(f, "Auto animation speed over frames. Effective z += frame * (z speed / 100).");

    Enumeration_knob(
        f,
        &phase_wrap_mode_,
        kWrapModes,
        "color_ramp_wrap_mode",
        "z wrap");
    Tooltip(f, "Phase wrap behavior: clamp, repeat, or pingpong.");

    if (Knob* divider = Divider(f)) {
      divider->name("color_ramp_divider_animation");
      divider->label("");
    }

    Double_knob(f, &color_ramp_mix_, "color_ramp_mix", "mix");
    SetRange(f, 0.0, 1.0);
    SetFlags(f, Knob::SLIDER);
    Tooltip(f, "Global effect mix.");

    if (f.makeKnobs()) {
      if (stops_knob) {
        color_ramp_table_ = stops_knob->tableKnob();
        ensure_color_ramp_table_defaults();
      }
      if (!sync_color_ramp_stops()) {
        ensure_color_ramp_table_defaults();
        sync_color_ramp_stops_from_table();
      }
      if (color_ramp_serialized_.empty() && !color_ramp_stops_.empty()) {
        sync_color_ramp_serialized_from_stops();
      }
      sync_selected_knobs_from_stops();
      sync_selected_knobs_to_ui();
    }
  }

  int knob_changed(Knob* k) override {
    const std::string name(k ? k->name() : "");
    if (syncing_selected_knobs_ &&
        (name == "color_ramp_selected_index" ||
         name == "color_ramp_pos" ||
         name == "color_ramp_color" ||
         name.rfind("color_ramp_color.", 0) == 0)) {
      return 1;
    }

    if (name == "color_ramp_stops" ||
        name.rfind("color_ramp_stops.", 0) == 0) {
      if (sync_color_ramp_stops_from_table()) {
        sync_color_ramp_serialized_from_stops();
        sync_selected_knobs_from_stops();
        sync_selected_knobs_to_ui();
      }
    } else if (name == "color_ramp_serialized") {
      if (sync_color_ramp_stops_from_serialized()) {
        sync_selected_knobs_from_stops();
        sync_selected_knobs_to_ui();
      }
    } else if (name == "color_ramp_interpolation" ||
               name == "color_ramp_zspeed" ||
               name == "color_ramp_mix") {
      phase_zspeed_ = std::max(0.0, phase_zspeed_);
      color_ramp_mix_ = std::max(0.0, std::min(1.0, color_ramp_mix_));
    } else if (name == "color_ramp_selected_index") {
      if (sync_color_ramp_stops()) {
        sync_selected_knobs_from_stops();
        sync_selected_knobs_to_ui();
      }
    } else if (name == "color_ramp_pos" ||
               name == "color_ramp_color" ||
               name.rfind("color_ramp_color.", 0) == 0) {
      if (sync_color_ramp_stops()) {
        apply_selected_knobs_to_stops();
        sync_color_ramp_serialized_from_stops();
        sync_selected_knobs_to_ui();
      }
    }
    return 1;
  }

  void append(Hash& hash) override {
    Iop::append(hash);
    hash.append(color_ramp_serialized_);
    hash.append(color_ramp_source_);
    hash.append(color_ramp_value_range_mode_);
    hash.append(color_ramp_interpolation_);
    hash.append(color_ramp_mix_);
    hash.append(color_ramp_blend_mode_);
    hash.append(phase_wrap_mode_);
    hash.append(phase_z_);
    hash.append(phase_zspeed_);
    if (phase_zspeed_ > 0.0) {
      hash.append(static_cast<float>(outputContext().frame()));
    }
    if (color_ramp_table_) {
      color_ramp_table_->knob().append(hash, &outputContext());
    }
  }

  const char* Class()     const override { return CLASS; }
  const char* node_help() const override { return HELP; }

  static const Iop::Description d;
};

static Iop* build(Node* node) { return new TColorRamp(node); }
const Iop::Description TColorRamp::d(CLASS, "Color/TColorRamp", build);

extern "C" void tcolor_ramp_keepalive() {}
extern "C" void FnPlugin_GetAPI(int) {}
