"""
Ray Train Checkpointing Script for RHOAI
Compatible with Ray Train v2 (no deprecated restore APIs)
"""
import os
import tempfile
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

from ray import train
from ray.train import Checkpoint, RunConfig, CheckpointConfig, ScalingConfig
from ray.train.torch import TorchTrainer

# Configuration
STORAGE_PATH = f"s3://{os.environ.get('AWS_S3_BUCKET', 'my-bucket')}/ray-checkpoints/mnist-demo"
RUN_NAME = "mnist-checkpointing-run"


class SimpleCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 32, 3, 1)
        self.conv2 = nn.Conv2d(32, 64, 3, 1)
        self.fc1 = nn.Linear(9216, 128)
        self.fc2 = nn.Linear(128, 10)
    
    def forward(self, x):
        x = torch.relu(self.conv1(x))
        x = torch.relu(self.conv2(x))
        x = torch.max_pool2d(x, 2)
        x = torch.flatten(x, 1)
        x = torch.relu(self.fc1(x))
        x = self.fc2(x)
        return x


def train_func(config):
    epochs = config.get("epochs", 10)
    batch_size = config.get("batch_size", 64)
    lr = config.get("lr", 0.001)
    
    # Setup data
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])
    train_dataset = datasets.MNIST('/tmp/data', train=True, download=True, transform=transform)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    train_loader = train.torch.prepare_data_loader(train_loader)
    
    # Setup model
    model = SimpleCNN()
    model = train.torch.prepare_model(model)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()
    
    # Checkpoint restore: auto-detect and resume
    start_epoch = 0
    checkpoint = train.get_checkpoint()
    if checkpoint:
        with checkpoint.as_directory() as checkpoint_dir:
            ckpt_path = os.path.join(checkpoint_dir, "checkpoint.pt")
            checkpoint_dict = torch.load(ckpt_path, weights_only=False)
            model.load_state_dict(checkpoint_dict["model_state_dict"])
            optimizer.load_state_dict(checkpoint_dict["optimizer_state_dict"])
            start_epoch = checkpoint_dict["epoch"] + 1
            print("=" * 60)
            print(f"RESUMING FROM CHECKPOINT - Starting at epoch {start_epoch}")
            print(f"Previous loss: {checkpoint_dict.get('loss', 'N/A')}")
            print("=" * 60)
    else:
        print("=" * 60)
        print("NO CHECKPOINT FOUND - Starting fresh training from epoch 0")
        print("=" * 60)
    
    # Training loop
    for epoch in range(start_epoch, epochs):
        model.train()
        total_loss = 0
        num_batches = 0
        
        for batch_idx, (data, target) in enumerate(train_loader):
            optimizer.zero_grad()
            output = model(data)
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            num_batches += 1
        
        avg_loss = total_loss / num_batches
        
        # Save checkpoint at end of each epoch
        with tempfile.TemporaryDirectory() as tmpdir:
            checkpoint_path = os.path.join(tmpdir, "checkpoint.pt")
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "loss": avg_loss,
            }, checkpoint_path)
            
            train.report(
                metrics={"loss": avg_loss, "epoch": epoch},
                checkpoint=Checkpoint.from_directory(tmpdir)
            )
        
        print(f"Epoch {epoch}/{epochs-1}: loss={avg_loss:.4f} [Checkpoint saved to S3]")


if __name__ == "__main__":
    import ray
    ray.init()
    
    print("=" * 60)
    print(f"Storage path: {STORAGE_PATH}")
    print(f"Run name: {RUN_NAME}")
    print("=" * 60)
    
    # Ray Train automatically detects and resumes from existing checkpoints
    # when using the same storage_path and run name. The train.get_checkpoint()
    # function inside train_func will return the latest checkpoint if one exists.
    trainer = TorchTrainer(
        train_func,
        train_loop_config={
            "epochs": 10,
            "batch_size": 64,
            "lr": 0.001,
        },
        scaling_config=ScalingConfig(
            num_workers=1,
            use_gpu=False,
        ),
        run_config=RunConfig(
            name=RUN_NAME,
            storage_path=STORAGE_PATH,
            checkpoint_config=CheckpointConfig(
                num_to_keep=3,
                checkpoint_score_attribute="loss",
                checkpoint_score_order="min",
            ),
        ),
    )
    
    result = trainer.fit()
    
    print("=" * 60)
    print("TRAINING COMPLETE")
    print(f"Final result path: {result.path}")
    print("=" * 60)