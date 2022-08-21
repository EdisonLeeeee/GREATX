import torch
import numpy as np
import torch_geometric.transforms as T

from greatx.dataset import GraphDataset
from greatx import set_seed
from greatx.nn.models import GCN
from greatx.training import Trainer
from greatx.training.callbacks import ModelCheckpoint
from greatx.utils import split_nodes
from greatx.attack.targeted import GFAttack

dataset = GraphDataset(root='~/data/pygdata', name='cora',
                       transform=T.LargestConnectedComponents())

data = dataset[0]
splits = split_nodes(data.y, random_state=15)
set_seed(123)
device = torch.device(
    'cuda') if torch.cuda.is_available() else torch.device('cpu')

# ================================================================== #
#                     Attack Setting                                 #
# ================================================================== #
target = 1  # target node to attack
target_label = data.y[target].item()
width = 5

# ================================================================== #
#                      Before Attack                                 #
# ================================================================== #
trainer_before = Trainer(
    GCN(data.x.size(-1), data.y.max().item() + 1), device=device)
ckp = ModelCheckpoint('model_before.pth', monitor='val_acc')
trainer_before.fit({'data': data, 'mask': splits.train_nodes},
                   {'data': data, 'mask': splits.val_nodes}, callbacks=[ckp])
trainer_before.cache_clear()
output = trainer_before.predict({'data': data, 'mask': target})
print(
    f"Before attack (target_label={target_label})\n {np.round(output.tolist(), 2)}")
print('-' * target_label * width + '----👆' + '-' *
      max(dataset.num_classes - target_label - 1, 0) * width)

# ================================================================== #
#                      Attacking                                     #
# ================================================================== #
# T=128 for citeseer and pubmed, T=data.num_nodes//2 for cora to reproduce results in paper, by the author
attacker = GFAttack(data, device=device, T=128)
attacker.reset()
attacker.attack(target)

# ================================================================== #
#                      After evasion Attack                          #
# ================================================================== #
output = trainer_before.predict({'data': attacker.data(), 'mask': target})
print(
    f"After evasion attack (target_label={target_label})\n {np.round(output.tolist(), 2)}")
print('-' * target_label * width + '----👆' + '-' *
      max(dataset.num_classes - target_label - 1, 0) * width)

# ================================================================== #
#                      After poisoning Attack                        #
# ================================================================== #
trainer_after = Trainer(
    GCN(data.x.size(-1), data.y.max().item() + 1), device=device)
ckp = ModelCheckpoint('model_after.pth', monitor='val_acc')
trainer_after.fit({'data': attacker.data(), 'mask': splits.train_nodes},
                  {'data': attacker.data(), 'mask': splits.val_nodes}, callbacks=[ckp])
trainer_after.cache_clear()
output = trainer_after.predict({'data': attacker.data(), 'mask': target})

print(
    f"After poisoning attack (target_label={target_label})\n {np.round(output.tolist(), 2)}")
print('-' * target_label * width + '----👆' + '-' *
      max(dataset.num_classes - target_label - 1, 0) * width)
