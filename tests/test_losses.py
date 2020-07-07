# -*- coding: utf-8 -*-

"""Test the PyKEEN custom loss functions."""

import unittest
from typing import Mapping

import torch

from pykeen.losses import BCEAfterSigmoidLoss, BCELoss, CrossEntropyLoss, Loss, MSELoss, MarginRankingLoss, NSSALoss, PairwiseLoss, PointwiseLoss, SetwiseLoss, SoftplusLoss, losses
from pykeen.pipeline import pipeline
from tests.base import GenericTest, TestsTest


class _LossTests(GenericTest[Loss]):
    """Base unittest for loss functions."""

    #: The batch size
    batch_size: int = 3

    #: Which training loops are supported
    # TODO: Make this part of the loss class
    training_loop_support: Mapping[str, bool] = dict(
        owa=True,
        lcwa=True,
    )

    @staticmethod
    def _check_loss_value(loss_value: torch.FloatTensor) -> None:
        """Check loss value dimensionality, and ability for backward."""
        # test reduction
        assert loss_value.ndim == 0

        # Test backward
        loss_value.backward()

    def test_consistent_default_reduction(self):
        """Verify that the default reduction equals 'mean'."""
        assert self.instance.reduction == 'mean'

    def test_cls_in_losses(self):
        """Verify that the loss class is in losses.losses"""
        assert self.cls in losses.values()

    def test_training_loops(self):
        """Verify that the loss can be used in the training pipeline with appropriate training loops."""
        for training_loop, applicable in self.training_loop_support.items():
            kwargs = dict(
                dataset='nations',
                model='transe',
                loss=self.cls,
                loss_kwargs=self.kwargs,
                training_loop=training_loop,
                training_kwargs=dict(
                    num_epochs=2,
                )
            )
            if applicable:
                pipeline(**kwargs)
            else:
                # TODO: Better exception specification
                with self.assertRaises(Exception):
                    pipeline(**kwargs)


class _PointwiseLossTests(_LossTests):
    """Base unit test for point-wise losses."""

    instance: PointwiseLoss

    #: The number of entities.
    num_entities: int = 17

    def test_forward(self):
        """Test ``forward(scores, labels)``."""
        scores = torch.rand(self.batch_size, self.num_entities, requires_grad=True)
        labels = torch.rand(self.batch_size, self.num_entities, requires_grad=False)
        loss_value = self.instance(
            scores=scores,
            labels=labels,
        )
        self._check_loss_value(loss_value=loss_value)

    def test_label_sanity_check(self):
        """Test that the losses check the labels for appropriate value range."""
        scores = torch.rand(self.batch_size, self.num_entities, requires_grad=True)

        # labels < 0
        with self.assertRaises(AssertionError):
            self.instance(
                scores=scores,
                labels=torch.empty(self.batch_size, self.num_entities, requires_grad=False).fill_(value=-0.1),
            )

        # labels > 1
        with self.assertRaises(AssertionError):
            self.instance(
                scores=scores,
                labels=torch.empty(self.batch_size, self.num_entities, requires_grad=False).fill_(value=1.1),
            )


class BCELossTests(_PointwiseLossTests, unittest.TestCase):
    """Unit test for BCELoss."""

    cls = BCELoss


class BCEAfterSigmoidLossTests(_PointwiseLossTests, unittest.TestCase):
    """Unit test for BCEAfterSigmoidLoss."""

    cls = BCEAfterSigmoidLoss


class MSELossTests(_PointwiseLossTests, unittest.TestCase):
    """Unit test for MSELoss."""

    cls = MSELoss


class SoftplusLossTests(_PointwiseLossTests, unittest.TestCase):
    """Unit test for SoftplusLoss."""

    cls = SoftplusLoss


class PointwiseLossTestsTest(TestsTest[PointwiseLoss], unittest.TestCase):
    """unittest for unittests for pointwise losses."""

    base_cls = PointwiseLoss
    base_test_cls = _PointwiseLossTests


class _PairwiseLossTests(_LossTests):
    """Base unit test for pair-wise losses."""

    instance: PairwiseLoss

    #: The number of negative samples
    num_negatives: int = 5

    def test_forward(self):
        """Test ``forward(pos_scores, neg_scores)``."""
        pos_scores = torch.rand(self.batch_size, 1, requires_grad=True)
        neg_scores = torch.rand(self.batch_size, self.num_negatives, requires_grad=True)
        loss_value = self.instance(
            pos_scores=pos_scores,
            neg_scores=neg_scores,
        )
        self._check_loss_value(loss_value=loss_value)


class MarginRankingLossTests(_PairwiseLossTests, unittest.TestCase):
    """Unittest for MarginRankingLoss."""

    cls = MarginRankingLoss


class NSSALossTests(_PairwiseLossTests, unittest.TestCase):
    """Unit test for NSSALoss."""

    cls = NSSALoss
    kwargs = dict(
        margin=1.,
        adversarial_temperature=1.,
    )

    def test_explicit_loss_values(self):
        assert self.kwargs['margin'] == 1.
        assert self.kwargs['adversarial_temperature'] == 1.

        pos_scores = torch.tensor([0., 0., -0.5, -0.5])
        neg_scores = torch.tensor([0., 0., -1., -1.])

        # ≈ result of softmax
        weights = torch.tensor([0.37, 0.37, 0.13, 0.13])

        # neg_distances - margin = [-1., -1., 0., 0.]
        # sigmoids ≈ [0.27, 0.27, 0.5, 0.5]
        log_sigmoids = torch.tensor([-1.31, -1.31, -0.69, -0.69])
        intermediate = weights * log_sigmoids
        neg_loss = torch.mean(intermediate, dim=-1)

        # pos_distances = [0., 0., 0.5, 0.5]
        # margin - pos_distances = [1. 1., 0.5, 0.5]
        # ≈ result of sigmoid
        # sigmoids ≈ [0.73, 0.73, 0.62, 0.62]
        log_sigmoids = torch.tensor([-0.31, -0.31, -0.48, -0.48])
        pos_loss = torch.mean(log_sigmoids)

        # expected_loss ≈ 0.34
        expected_loss = (-pos_loss - neg_loss) / 2.

        loss = self.instance(pos_scores, neg_scores).item()

        self.assertAlmostEqual(expected_loss, 0.34, delta=0.02)
        self.assertAlmostEqual(expected_loss, loss, delta=0.02)


class PairwiseLossTestsTest(TestsTest[PairwiseLoss], unittest.TestCase):
    """unittest for unittests for pairwise losses."""

    base_cls = PairwiseLoss
    base_test_cls = _PairwiseLossTests


class _SetwiseLossTests(_LossTests):
    """unittests for setwise losses."""

    instance: SetwiseLoss

    #: Setwise do not support owa training loop
    training_loop_support = dict(
        owa=False,
        lcwa=True,
    )

    #: The number of entities.
    num_entities: int = 13

    def test_forward(self):
        """Test forward(scores, labels)."""
        scores = torch.rand(self.batch_size, self.num_entities, requires_grad=True)
        labels = torch.rand(self.batch_size, self.num_entities, requires_grad=False)
        loss_value = self.instance(
            scores=scores,
            labels=labels,
        )
        self._check_loss_value(loss_value=loss_value)


class CrossEntropyLossTests(_SetwiseLossTests, unittest.TestCase):
    """Unit test for CrossEntropyLoss."""

    cls = CrossEntropyLoss


class LossTestTests(TestsTest, unittest.TestCase):
    """Unittest for unittests for all losses."""

    base_cls = Loss
    base_test_cls = _LossTests
    skip_cls = {PointwiseLoss, PairwiseLoss, SetwiseLoss}
