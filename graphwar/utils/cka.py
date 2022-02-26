import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from functools import partial
from warnings import warn
from typing import List, Dict

import matplotlib.pyplot as plt
from mpl_toolkits import axes_grid1


def add_colorbar(im, aspect=10, pad_fraction=0.5, **kwargs):
    """Add a vertical color bar to an image plot."""
    divider = axes_grid1.make_axes_locatable(im.axes)
    width = axes_grid1.axes_size.AxesY(im.axes, aspect=1./aspect)
    pad = axes_grid1.axes_size.Fraction(pad_fraction, width)
    current_ax = plt.gca()
    cax = divider.append_axes("right", size=width, pad=pad)
    plt.sca(current_ax)
    return im.axes.figure.colorbar(im, cax=cax, **kwargs)


class CKA:
    """Centered Kernel Alignment (CKA) metric, where the features of the networks are compared.
    See https://github.com/AntixK/PyTorch-Model-Compare
    """

    def __init__(self,
                 model1: nn.Module,
                 model2: nn.Module,
                 model1_name: str = None,
                 model2_name: str = None,
                 model1_layers: List[str] = None,
                 model2_layers: List[str] = None,
                 device: str = 'cpu'):
        """

        Parameters
        ----------
        model1 : nn.Module
            model 1
        model2 : nn.Module
            model 2
        model1_name : str, optional
            name of model 1, by default None
        model2_name : str, optional
            name of model 2, by default None
        model1_layers : List[str], optional
            List of layers to extract features from, by default None
        model2_layers : List[str], optional
            List of layers to extract features from, by default None
        device : str, optional
            device to run the models, by default 'cpu'

        Example
        -------
        >>> g = ... # get your graph
        >>> trainer1 = ... # get your trainer1
        >>> trainer2 = ... # get your trainer2
        >>> dataloader = trainer1.config_test_data(g)
        >>> m1 = trainer1.model
        >>> m2 = trainer2.model
        >>> cka = CKA(m1, m2)
        >>> cka.compare(dataloader)
        >>> cka.plot_results()

        """
        self.model1 = model1
        self.model2 = model2

        self.device = torch.device(device)

        self.model1_info = {}
        self.model2_info = {}

        if model1_name is None:
            self.model1_info['Name'] = model1.__repr__().split('(')[0]
        else:
            self.model1_info['Name'] = model1_name

        if model2_name is None:
            self.model2_info['Name'] = model2.__repr__().split('(')[0]
        else:
            self.model2_info['Name'] = model2_name

        if self.model1_info['Name'] == self.model2_info['Name']:
            warn(f"Both model have identical names - {self.model2_info['Name']}. "
                 "It may cause confusion when interpreting the results. "
                 "Consider giving unique names to the models :)")

        self.model1_info['Layers'] = []
        self.model2_info['Layers'] = []

        self.model1_features = {}
        self.model2_features = {}

        if len(list(model1.modules())) > 150 and model1_layers is None:
            warn("Model 1 seems to have a lot of layers. "
                 "Consider giving a list of layers whose features you are concerned with "
                 "through the 'model1_layers' parameter. Your CPU/GPU will thank you :)")

        self.model1_layers = model1_layers

        if len(list(model2.modules())) > 150 and model2_layers is None:
            warn("Model 2 seems to have a lot of layers. "
                 "Consider giving a list of layers whose features you are concerned with "
                 "through the 'model2_layers' parameter. Your CPU/GPU will thank you :)")

        self.model2_layers = model2_layers

        self._insert_hooks()
        self.model1 = self.model1.to(self.device)
        self.model2 = self.model2.to(self.device)

        self.model1.eval()
        self.model2.eval()

    def _log_layer(self,
                   model: str,
                   name: str,
                   layer: nn.Module,
                   inp: torch.Tensor,
                   out: torch.Tensor):
        if out.ndim != 2:
            # ignore those features that dimensions not equal to 2
            return

        if model == "model1":
            self.model1_features[name] = out

        elif model == "model2":
            self.model2_features[name] = out

        else:
            raise RuntimeError("Unknown model name for _log_layer.")

    def _insert_hooks(self):

        # Model 1
        for name, layer in self.model1.named_modules():
            if self.model1_layers is not None:
                if name in self.model1_layers:
                    self.model1_info['Layers'] += [name]
                    layer.register_forward_hook(
                        partial(self._log_layer, "model1", name))
            else:
                self.model1_info['Layers'] += [name]
                layer.register_forward_hook(
                    partial(self._log_layer, "model1", name))

        # Model 2
        for name, layer in self.model2.named_modules():
            if self.model2_layers is not None:
                if name in self.model2_layers:
                    self.model2_info['Layers'] += [name]
                    layer.register_forward_hook(
                        partial(self._log_layer, "model2", name))
            else:

                self.model2_info['Layers'] += [name]
                layer.register_forward_hook(
                    partial(self._log_layer, "model2", name))

    def _HSIC(self, K, L):
        """
        Computes the unbiased estimate of HSIC metric.
        Reference: https://arxiv.org/pdf/2010.15327.pdf Eq (3)
        """
        N = K.shape[0]
        ones = torch.ones(N, 1).to(self.device)
        result = torch.trace(K @ L)
        result += ((ones.t() @ K @ ones @ ones.t() @ L @ ones) /
                   ((N - 1) * (N - 2))).item()
        result -= ((ones.t() @ K @ L @ ones) * 2 / (N - 2)).item()
        result = (1 / (N * (N - 3)) * result).item()
        return result

    @torch.no_grad()
    def compare(self,
                dataloader1: DataLoader,
                dataloader2: DataLoader = None) -> None:
        """
        Computes the feature similarity between the models on the
        given datasets.

        Parameters
        ----------
        dataloader1 : DataLoader
            the dataset where model 1 run on.
        dataloader2 : DataLoader, optional
            If given, model 2 will run on this dataset. by default None
        """

        if dataloader2 is None:
            warn(
                "Dataloader for Model 2 is not given. Using the same dataloader for both models.")
            dataloader2 = dataloader1

#         self.model1_info['Dataset'] = dataloader1.dataset.__repr__().split('\n')[0]
#         self.model2_info['Dataset'] = dataloader2.dataset.__repr__().split('\n')[0]

        self.model1_features = {}
        self.model2_features = {}
        self.model1.eval()
        self.model2.eval()

        for data, *_ in dataloader1:
            _ = self.model1(*data)
            break

        for data, *_ in dataloader2:
            _ = self.model2(*data)
            break

        N = len(self.model1_layers) if self.model1_layers is not None else len(
            self.model1_features)
        M = len(self.model2_layers) if self.model2_layers is not None else len(
            self.model2_features)
        num_batches = 1

        self.hsic_matrix = torch.zeros(N, M, 3)

        for i, (name1, feat1) in enumerate(self.model1_features.items()):
            X = feat1.flatten(1)
            K = X @ X.t()
            K.fill_diagonal_(0.0)
            self.hsic_matrix[i, :, 0] += self._HSIC(K, K) / num_batches

            for j, (name2, feat2) in enumerate(self.model2_features.items()):
                Y = feat2.flatten(1)
                L = Y @ Y.t()
                L.fill_diagonal_(0)
                assert K.shape == L.shape, f"Feature shape mistach! {K.shape}, {L.shape}"

                self.hsic_matrix[i, j, 1] += self._HSIC(K, L) / num_batches
                self.hsic_matrix[i, j, 2] += self._HSIC(L, L) / num_batches
        self.hsic_matrix = self.hsic_matrix[:, :, 1] / (self.hsic_matrix[:, :, 0].sqrt() *
                                                        self.hsic_matrix[:, :, 2].sqrt())

        assert not torch.isnan(self.hsic_matrix).any(
        ), "HSIC computation resulted in NANs"
        return self

    def export(self) -> Dict:
        """
        Exports the CKA data along with the respective model layer names.
        :return:
        """
        return {
            "model1_name": self.model1_info['Name'],
            "model2_name": self.model2_info['Name'],
            "CKA": self.hsic_matrix,
            "model1_layers": self.model1_info['Layers'],
            "model2_layers": self.model2_info['Layers'],

        }

    def plot_results(self,
                     save_path: str = None,
                     title: str = None):
        fig, ax = plt.subplots()
        im = ax.imshow(self.hsic_matrix, origin='lower', cmap='magma')
        ax.set_xlabel(f"Layers {self.model2_info['Name']}", fontsize=15)
        ax.set_ylabel(f"Layers {self.model1_info['Name']}", fontsize=15)

        if title is not None:
            ax.set_title(f"{title}", fontsize=18)
        else:
            ax.set_title(
                f"{self.model1_info['Name']} vs {self.model2_info['Name']}", fontsize=18)

        add_colorbar(im)
        plt.tight_layout()

        if save_path is not None:
            plt.savefig(save_path, dpi=300)

        plt.show()
