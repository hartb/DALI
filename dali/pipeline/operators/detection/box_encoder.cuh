// Copyright (c) 2017-2018, NVIDIA CORPORATION. All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifndef DALI_PIPELINE_OPERATORS_DETECTION_BOX_ENCODER_CUH_
#define DALI_PIPELINE_OPERATORS_DETECTION_BOX_ENCODER_CUH_

#include <utility>
#include <vector>

#include "dali/kernels/tensor_shape.h"
#include "dali/pipeline/operators/detection/box_encoder.h"

namespace dali {
template <>
class BoxEncoder<GPUBackend> : public Operator<GPUBackend> {
 public:
  static constexpr int BlockSize = 256;

  explicit BoxEncoder(const OpSpec &spec)
      : Operator<GPUBackend>(spec),
        criteria_(spec.GetArgument<float>("criteria")),
        offset_(spec.GetArgument<bool>("offset")),
        scale_(spec.GetArgument<float>("scale")) {
    DALI_ENFORCE(criteria_ >= 0.f,
                 "Expected criteria >= 0, actual value = " + std::to_string(criteria_));
    DALI_ENFORCE(criteria_ <= 1.f,
                 "Expected criteria <= 1, actual value = " + std::to_string(criteria_));

    PrepareAnchors(spec.GetArgument<vector<float>>("anchors"));

    boxes_offsets_.Resize({batch_size_ + 1});

    best_box_idx_.Resize({batch_size_ * anchors_count_});
    best_box_iou_.Resize({batch_size_ * anchors_count_});

    auto means = spec.GetArgument<vector<float>>("means");
    DALI_ENFORCE(means.size() == BoundingBox::kSize,
      "means size must be a list of 4 values.");

    means_.Resize({BoundingBox::kSize});
    auto means_data = means_.mutable_data<float>();
    MemCopy(means_data, means.data(), BoundingBox::kSize * sizeof(float));

    auto stds = spec.GetArgument<vector<float>>("stds");
    DALI_ENFORCE(stds.size() == BoundingBox::kSize,
      "stds size must be a list of 4 values.");
    DALI_ENFORCE(std::find(stds.begin(), stds.end(), 0) == stds.end(),
       "stds values must be != 0.");
    stds_.Resize({BoundingBox::kSize});
    auto stds_data = stds_.mutable_data<float>();
    MemCopy(stds_data, stds.data(), BoundingBox::kSize * sizeof(float));
  }

  virtual ~BoxEncoder() = default;

  DISABLE_COPY_MOVE_ASSIGN(BoxEncoder);

 protected:
  void RunImpl(Workspace<GPUBackend> *ws, const int idx) override;

 private:
  static constexpr int kBoxesOutputDim = 2;
  static constexpr int kLabelsOutputDim = 1;
  const float criteria_;
  int64_t anchors_count_;
  Tensor<GPUBackend> anchors_;
  Tensor<GPUBackend> anchors_as_center_wh_;
  Tensor<GPUBackend> boxes_offsets_;
  Tensor<GPUBackend> best_box_idx_;
  Tensor<GPUBackend> best_box_iou_;

  bool offset_;
  Tensor<GPUBackend> means_;
  Tensor<GPUBackend> stds_;
  float scale_;

  std::pair<int*, float*> ClearBuffers(const cudaStream_t &stream);

  void PrepareAnchors(const vector<float> &anchors);

  void WriteAnchorsToOutput(
    float4 *out_boxes, int *out_labels, const cudaStream_t &stream);

  void ClearOutput(
    float4 *out_boxes, int *out_labels, const cudaStream_t &stream);

  std::pair<kernels::TensorListShape<>, kernels::TensorListShape<>> CalculateDims(
    const TensorList<GPUBackend> &boxes_input);

  int *CalculateBoxesOffsets(
    const TensorList<GPUBackend> &boxes_input, const cudaStream_t &stream);
};
}  // namespace dali

#endif
