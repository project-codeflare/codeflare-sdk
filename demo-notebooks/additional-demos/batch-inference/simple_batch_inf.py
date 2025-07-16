import ray
from ray.data.llm import build_llm_processor, vLLMEngineProcessorConfig


# 1. Construct a vLLM processor config.
processor_config = vLLMEngineProcessorConfig(
    # The base model.
    model_source="unsloth/Llama-3.2-1B-Instruct",
    # vLLM engine config.
    engine_kwargs=dict(
        enable_lora=False,
        # # Older GPUs (e.g. T4) don't support bfloat16. You should remove
        # # this line if you're using later GPUs.
        dtype="half",
        # Reduce the model length to fit small GPUs. You should remove
        # this line if you're using large GPUs.
        max_model_len=1024,
    ),
    # The batch size used in Ray Data.
    batch_size=8,
    # Use one GPU in this example.
    concurrency=1,
    # If you save the LoRA adapter in S3, you can set the following path.
    # dynamic_lora_loading_path="s3://your-lora-bucket/",
)

# 2. Construct a processor using the processor config.
processor = build_llm_processor(
    processor_config,
    preprocess=lambda row: dict(
        # Remove the LoRA model specification
        messages=[
            {
                "role": "system",
                "content": "You are a calculator. Please only output the answer "
                "of the given equation.",
            },
            {"role": "user", "content": f"{row['id']} ** 3 = ?"},
        ],
        sampling_params=dict(
            temperature=0.3,
            max_tokens=20,
            detokenize=False,
        ),
    ),
    postprocess=lambda row: {
        "resp": row["generated_text"],
    },
)

# 3. Synthesize a dataset with 32 rows.
ds = ray.data.range(32)
# 4. Apply the processor to the dataset. Note that this line won't kick off
# anything because processor is execution lazily.
ds = processor(ds)
# Materialization kicks off the pipeline execution.
ds = ds.materialize()

# 5. Print all outputs.
for out in ds.take_all():
    print(out)
    print("==========")
