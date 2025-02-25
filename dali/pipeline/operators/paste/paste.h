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

#ifndef DALI_PIPELINE_OPERATORS_PASTE_PASTE_H_
#define DALI_PIPELINE_OPERATORS_PASTE_PASTE_H_

#include <cstring>
#include <utility>
#include <vector>
#include <random>

#include "dali/core/common.h"
#include "dali/pipeline/operators/common.h"
#include "dali/core/error_handling.h"
#include "dali/pipeline/operators/operator.h"

namespace dali {

template <typename Backend>
class Paste : public Operator<Backend> {
 public:
  // 6 values: in_H, in_W, out_H, out_W, paste_y, paste_x
  static const int NUM_INDICES = 6;

  explicit inline Paste(const OpSpec &spec) :
    Operator<Backend>(spec),
    C_(spec.GetArgument<int>("n_channels")) {
    // Kind of arbitrary, we need to set some limit here
    // because we use static shared memory for storing
    // fill value array
    DALI_ENFORCE(C_ <= 1024,
      "n_channels of more than 1024 is not supported");
    std::vector<uint8> rgb;
    GetSingleOrRepeatedArg(spec, rgb, "fill_value", C_);
    fill_value_.Copy(rgb, 0);

    input_ptrs_.Resize({batch_size_});
    output_ptrs_.Resize({batch_size_});
    in_out_dims_paste_yx_.Resize({batch_size_ * NUM_INDICES});
  }

  virtual inline ~Paste() = default;

 protected:
  void RunImpl(Workspace<Backend> *ws, const int idx) override;

  void SetupSharedSampleParams(Workspace<Backend> *ws) override;

  void SetupSampleParams(Workspace<Backend> *ws, const int idx);

  void RunHelper(Workspace<Backend> *ws);

  // Op parameters
  int C_;
  Tensor<Backend> fill_value_;

  Tensor<CPUBackend> input_ptrs_, output_ptrs_, in_out_dims_paste_yx_;
  Tensor<GPUBackend> input_ptrs_gpu_, output_ptrs_gpu_, in_out_dims_paste_yx_gpu_;

  USE_OPERATOR_MEMBERS();
  using Operator<Backend>::RunImpl;
};

}  // namespace dali

#endif  // DALI_PIPELINE_OPERATORS_PASTE_PASTE_H_
