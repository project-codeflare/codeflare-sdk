import os
import tempfile

import torch
from torch.utils.data import DataLoader, DistributedSampler
from torchvision.models import resnet18
from torchvision.datasets import FashionMNIST
from torchvision.transforms import ToTensor, Normalize, Compose
import lightning.pytorch as pl

import ray.train.lightning
from ray.train.torch import TorchTrainer

# Based on https://docs.ray.io/en/latest/train/getting-started-pytorch-lightning.html

"""
Note: This example requires an S3 compatible storage bucket for distributed training. Please visit our documentation for more information -> https://github.com/project-codeflare/codeflare-sdk/blob/main/docs/s3-compatible-storage.md
"""


# Model, Loss, Optimizer
class ImageClassifier(pl.LightningModule):
    def __init__(self):
        super(ImageClassifier, self).__init__()
        self.model = resnet18(num_classes=10)
        self.model.conv1 = torch.nn.Conv2d(
            1, 64, kernel_size=(7, 7), stride=(2, 2), padding=(3, 3), bias=False
        )
        self.criterion = torch.nn.CrossEntropyLoss()

    def forward(self, x):
        return self.model(x)

    def training_step(self, batch, batch_idx):
        x, y = batch
        outputs = self.forward(x)
        loss = self.criterion(outputs, y)
        self.log("loss", loss, on_step=True, prog_bar=True)
        return loss

    def configure_optimizers(self):
        return torch.optim.Adam(self.model.parameters(), lr=0.001)


def train_func():
    # Data
    transform = Compose([ToTensor(), Normalize((0.5,), (0.5,))])
    data_dir = os.path.join(tempfile.gettempdir(), "data")
    train_data = FashionMNIST(
        root=data_dir, train=True, download=True, transform=transform
    )

    # Training
    model = ImageClassifier()

    sampler = DistributedSampler(
        train_data,
        num_replicas=ray.train.get_context().get_world_size(),
        rank=ray.train.get_context().get_world_rank(),
    )

    train_dataloader = DataLoader(
        train_data, batch_size=128, shuffle=False, sampler=sampler
    )
    # [1] Configure PyTorch Lightning Trainer.
    trainer = pl.Trainer(
        max_epochs=10,
        devices="auto",
        accelerator="auto",
        strategy=ray.train.lightning.RayDDPStrategy(),
        plugins=[ray.train.lightning.RayLightningEnvironment()],
        callbacks=[ray.train.lightning.RayTrainReportCallback()],
        # [1a] Optionally, disable the default checkpointing behavior
        # in favor of the `RayTrainReportCallback` above.
        enable_checkpointing=False,
    )
    trainer = ray.train.lightning.prepare_trainer(trainer)
    trainer.fit(model, train_dataloaders=train_dataloader)


# [2] Configure scaling and resource requirements. Set the number of workers to the total number of GPUs on your Ray Cluster.
scaling_config = ray.train.ScalingConfig(num_workers=3, use_gpu=True)

# [3] Launch distributed training job.
trainer = TorchTrainer(
    train_func,
    scaling_config=scaling_config,
)
result: ray.train.Result = trainer.fit()

# [4] Load the trained model.
with result.checkpoint.as_directory() as checkpoint_dir:
    model = ImageClassifier.load_from_checkpoint(
        os.path.join(
            checkpoint_dir,
            ray.train.lightning.RayTrainReportCallback.CHECKPOINT_NAME,
        ),
    )
