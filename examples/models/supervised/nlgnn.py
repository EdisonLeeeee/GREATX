import torch
import torch_geometric.transforms as T
from torch_geometric.datasets import Planetoid

from greatx.nn.models import NLGAT, NLGCN, NLMLP
from greatx.training.callbacks import ModelCheckpoint
from greatx.training.trainer import Trainer
from greatx.utils import split_nodes

dataset = Planetoid(root='~/data/pygdata', name='Cora')
data = dataset[0]
# use 60/20/20 splits according to the paper
splits = split_nodes(data.y, train=0.6, val=0.2, test=0.2, random_state=15)


device = torch.device(
    'cuda') if torch.cuda.is_available() else torch.device('cpu')
model = NLGCN(data.x.size(-1), data.y.max().item() + 1)
# model = NLMLP(data.x.size(-1), data.y.max().item() + 1)
# model = NLGAT(data.x.size(-1), data.y.max().item() + 1)
trainer = Trainer(model, device=device)
ckp = ModelCheckpoint('model.pth', monitor='val_acc')
trainer.fit({'data': data, 'mask': splits.train_nodes},
            {'data': data, 'mask': splits.val_nodes}, callbacks=[ckp])
trainer.evaluate({'data': data, 'mask': splits.test_nodes})