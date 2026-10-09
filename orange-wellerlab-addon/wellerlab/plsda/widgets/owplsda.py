"""
OWPLSDA widget — Partial Least Squares Discriminant Analysis.

Provides a PLS-DA classification widget for Orange3 that works with
categorical (discrete) class variables, unlike the existing PLS-R widget
which only works with numeric targets.
"""

import numpy as np
from AnyQt.QtCore import Qt

from Orange.data import Table, Domain, ContinuousVariable, DiscreteVariable, \
    StringVariable
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.owlearnerwidget import OWBaseLearner
from Orange.widgets.utils.signals import Output
from Orange.widgets.utils.widgetpreview import WidgetPreview
from Orange.widgets.widget import Msg

from wellerlab.plsda import PLSDALearner


class OWPLSDA(OWBaseLearner):
    name = "PLS-DA"
    description = "Partial Least Squares Discriminant Analysis " \
                  "for classification with categorical targets."
    icon = "icons/PLSDA.svg"
    priority = 86
    keywords = ["partial least squares", "discriminant analysis",
                "classification", "PLS-DA"]

    LEARNER = PLSDALearner

    class Outputs(OWBaseLearner.Outputs):
        data = Output(
            "Data with Scores",
            Table,
            default=True,
        )
        components = Output(
            "Components",
            Table,
            explicit=True,
        )

    class Warning(OWBaseLearner.Warning):
        few_features = Msg(
            "Number of components reduced to match data dimensions."
        )

    n_components = Setting(2)
    max_iter = Setting(500)
    scale = Setting(True)

    def add_main_layout(self):
        """Build the widget's control area UI."""
        optimization_box = gui.vBox(
            self.controlArea, "Optimization Parameters"
        )
        gui.spin(
            optimization_box, self, "n_components", 1, 50, 1,
            label="Components: ",
            alignment=Qt.AlignRight, controlWidth=100,
            callback=self.settings_changed,
        )
        gui.spin(
            optimization_box, self, "max_iter", 5, 1000000, 50,
            label="Iteration limit: ",
            alignment=Qt.AlignRight, controlWidth=100,
            callback=self.settings_changed,
            checkCallback=self.settings_changed,
        )
        gui.checkBox(
            optimization_box, self, "scale",
            "Scale features",
            callback=self.settings_changed,
        )

    def create_learner(self):
        return PLSDALearner(
            n_components=self.n_components,
            scale=self.scale,
            max_iter=self.max_iter,
            preprocessors=self.preprocessors,
        )

    def update_model(self):
        """Called after the model is (re-)trained. Sends outputs."""
        super().update_model()

        data_with_scores = None
        components_table = None

        if self.model is not None:
            data_with_scores = self._create_output_data()
            components_table = self._create_output_components()

        self.Outputs.data.send(data_with_scores)
        self.Outputs.components.send(components_table)

    def _create_output_data(self):
        """Create a table with PLS scores, predicted classes, and probabilities.

        Augments the input data with:
        - PLS X-scores (T1, T2, ...)
        - PLS Y-scores (U1, U2, ...)
        - Predicted class
        - Class probabilities (one column per class value)
        """
        data = self.data
        model = self.model

        # Transform data through the model's domain (handles preprocessing
        # like one-hot encoding of categorical features, scaling, etc.)
        model_data = model.data_to_model_domain(data)

        # Project into PLS space via the model
        n_comp = model.skl_model.n_components
        x_scores = model.skl_model.transform(model_data.X)

        # Predict class and get probabilities
        raw_scores = model.skl_model.predict(model_data.X)
        if raw_scores.ndim == 1:
            raw_scores = raw_scores.reshape(-1, 1)
        pred_class = np.argmax(raw_scores, axis=1)

        # Softmax probabilities
        exp_s = np.exp(raw_scores - raw_scores.max(axis=1, keepdims=True))
        probs = exp_s / exp_s.sum(axis=1, keepdims=True)

        # Build augmented domain
        class_var = data.domain.class_var
        score_names_x = [f"T{i + 1}" for i in range(n_comp)]
        prob_names = [
            f"p({class_var.name}={v})" for v in class_var.values
        ]

        # Add PLS scores as attributes
        new_attrs = data.domain.attributes \
            + tuple(ContinuousVariable(n) for n in score_names_x)

        # Add predicted class and probabilities as metas
        new_metas = data.domain.metas \
            + (DiscreteVariable("Predicted", values=class_var.values),) \
            + tuple(ContinuousVariable(n) for n in prob_names)

        new_domain = Domain(new_attrs, data.domain.class_vars, new_metas)

        # Build augmented data by transforming original data to new domain,
        # then filling in the new columns
        aug_data = data.transform(new_domain)

        # Fill in PLS scores (first new attributes)
        n_orig_attrs = len(data.domain.attributes)
        with aug_data.unlocked(aug_data.X):
            aug_data.X[:, n_orig_attrs:n_orig_attrs + n_comp] = x_scores

        # Fill in predicted class and probabilities (last metas)
        with aug_data.unlocked(aug_data.metas):
            aug_data.metas[:, -len(prob_names) - 1] = pred_class.astype(float)
            aug_data.metas[:, -len(prob_names):] = probs

        aug_data.name = f"{data.name} - PLS-DA scores"
        return aug_data

    def _create_output_components(self):
        """Build a components (loadings) table showing X and Y loadings."""
        model = self.model
        skl = model.skl_model

        n_components = skl.x_loadings_.shape[1]

        # X loadings — use model domain attributes which match preprocessed features
        attr_names = [a.name for a in model.domain.attributes]
        comp_names = [f"Comp {i + 1}" for i in range(n_components)]

        dom = Domain(
            [ContinuousVariable(n) for n in comp_names],
            metas=[StringVariable("Variable")],
        )

        X = skl.x_loadings_  # n_features x n_comp
        metas = np.array(attr_names, dtype=object).reshape(-1, 1)

        components = Table.from_numpy(dom, X=X, metas=metas)
        components.name = "PLS-DA components (X loadings)"
        return components


if __name__ == "__main__":  # pragma: no cover
    WidgetPreview(OWPLSDA).run(Table("zoo"))