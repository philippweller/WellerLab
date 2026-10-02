"""
OWOPLSDA widget — OPLS-DA (Orthogonal Partial Least Squares
Discriminant Analysis) with S-Plot for biomarker discovery.

Separates predictive from orthogonal variation and provides
an S-Plot visualization for variable selection.
"""

import numpy as np
from AnyQt.QtCore import Qt
from AnyQt.QtGui import QColor, QPen

import pyqtgraph as pg
from pyqtgraph import PlotWidget

from Orange.data import Table, Domain, ContinuousVariable, DiscreteVariable, \
    StringVariable
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.owlearnerwidget import OWBaseLearner
from Orange.widgets.utils.signals import Output
from Orange.widgets.utils.widgetpreview import WidgetPreview
from Orange.widgets.widget import Msg

from orangeplsda import OPLSDALearner


class OWOPLSDA(OWBaseLearner):
    name = "OPLS-DA"
    description = "Orthogonal Partial Least Squares Discriminant Analysis " \
                  "with S-Plot for biomarker discovery."
    icon = "icons/OPLSDA.svg"
    priority = 87
    keywords = ["orthogonal partial least squares", "discriminant analysis",
                "classification", "OPLS-DA", "S-Plot", "biomarker"]

    LEARNER = OPLSDALearner

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
        splot_data = Output(
            "S-Plot Data",
            Table,
            explicit=True,
        )
        biomarkers = Output(
            "Selected Biomarkers",
            Table,
            explicit=True,
        )

    n_components = Setting(1)
    n_ortho = Setting(1)
    scale = Setting(True)
    max_iter = Setting(500)

    want_main_area = True
    resizing_enabled = True

    def __init__(self):
        super().__init__()
        self.splot_p = None
        self.splot_pcorr = None
        self.splot_feature_names = None

        # Plot area for S-Plot
        self.plot_widget = pg.PlotWidget(
            title="S-Plot (P(corr) vs P)"
        )
        self.plot_widget.setLabel("bottom", "P — Covariance Loading")
        self.plot_widget.setLabel("left", "P(corr) — Correlation Loading")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setAspectLocked(False)
        self.mainArea.layout().addWidget(self.plot_widget)

        self.scatter_item = None
        self.selected_indices = []

    def add_main_layout(self):
        box = gui.vBox(self.controlArea, "Optimization Parameters")
        gui.spin(
            box, self, "n_components", 1, 10, 1,
            label="Predictive components: ",
            alignment=Qt.AlignRight, controlWidth=80,
            callback=self.settings_changed,
        )
        gui.spin(
            box, self, "n_ortho", 0, 20, 1,
            label="Orthogonal components: ",
            alignment=Qt.AlignRight, controlWidth=80,
            callback=self.settings_changed,
        )
        gui.spin(
            box, self, "max_iter", 5, 1000000, 50,
            label="Iteration limit: ",
            alignment=Qt.AlignRight, controlWidth=100,
            callback=self.settings_changed,
            checkCallback=self.settings_changed,
        )
        gui.checkBox(
            box, self, "scale",
            "Scale features",
            callback=self.settings_changed,
        )

    def create_learner(self):
        return OPLSDALearner(
            n_components=self.n_components,
            n_ortho=self.n_ortho,
            scale=self.scale,
            max_iter=self.max_iter,
            preprocessors=self.preprocessors,
        )

    def update_model(self):
        super().update_model()
        data_with_scores = None
        components_table = None
        splot_table = None
        biomarkers_table = None

        if self.model is not None:
            data_with_scores = self._create_output_data()
            components_table = self._create_output_components()
            splot_table = self._create_splot_table()
            biomarkers_table = self._compute_biomarkers()
            self._draw_splot()

        self.Outputs.data.send(data_with_scores)
        self.Outputs.components.send(components_table)
        self.Outputs.splot_data.send(splot_table)
        self.Outputs.biomarkers.send(biomarkers_table)

    def _create_output_data(self):
        """Augment data with OPLS scores and predictions."""
        data = self.data
        model = self.model
        model_data = model.data_to_model_domain(data)
        Xt = model_data.X

        # Deflate and get scores
        X_scaled = (Xt - model.x_mean) / model.x_std \
            if model.scaled else Xt - model.x_mean
        Xd = X_scaled.copy()
        for i in range(model.n_ortho):
            t_o = Xd @ model.w_ortho[i].ravel()
            Xd -= np.outer(t_o, model.p_ortho[i].ravel())
        t_pred = Xd @ model.w_pred.ravel()

        # Orthogonal scores
        ortho_names = []
        for i in range(model.n_ortho):
            ortho_names.append(f"t_o{i + 1}")

        # Predicted class + probabilities
        y_raw = model._predict_raw(Xt)
        if y_raw.ndim == 1:
            y_raw = y_raw.reshape(-1, 1)
        pred_class = np.argmax(y_raw, axis=1)
        y_max = y_raw.max(axis=1, keepdims=True)
        exp_s = np.exp(y_raw - y_max)
        probs = exp_s / exp_s.sum(axis=1, keepdims=True)

        class_var = data.domain.class_var
        score_names = ["t_pred"] + ortho_names
        prob_names = [
            f"p({class_var.name}={v})" for v in class_var.values
        ]

        new_attrs = data.domain.attributes \
            + tuple(ContinuousVariable(n) for n in score_names)
        new_metas = data.domain.metas \
            + (DiscreteVariable("Predicted", values=class_var.values),) \
            + tuple(ContinuousVariable(n) for n in prob_names)

        new_domain = Domain(new_attrs, data.domain.class_vars, new_metas)
        aug_data = data.transform(new_domain)

        n_orig_attrs = len(data.domain.attributes)
        n_new_attr = len(score_names)
        with aug_data.unlocked(aug_data.X):
            aug_data.X[:, n_orig_attrs] = t_pred
            for i in range(model.n_ortho):
                t_o_idx = n_orig_attrs + 1 + i
                if t_o_idx < aug_data.X.shape[1]:
                    Xd2 = X_scaled.copy()
                    for j in range(i + 1):
                        tt = Xd2 @ model.w_ortho[j].ravel()
                        Xd2 -= np.outer(tt, model.p_ortho[j].ravel())
                    aug_data.X[:, t_o_idx] = Xd2 @ model.w_ortho[i].ravel()

        with aug_data.unlocked(aug_data.metas):
            aug_data.metas[:, -len(prob_names) - 1] = pred_class.astype(float)
            aug_data.metas[:, -len(prob_names):] = probs

        aug_data.name = f"{data.name} - OPLS-DA scores"
        return aug_data

    def _create_output_components(self):
        """Return a Table of predictive and orthogonal loadings."""
        model = self.model
        n_total = 1 + model.n_ortho
        comp_names = ["Predictive"] + [f"Ortho {i + 1}" for i in range(model.n_ortho)]

        attr_names = [a.name for a in model.domain.attributes]
        dom = Domain(
            [ContinuousVariable(n) for n in comp_names],
            metas=[StringVariable("Variable")],
        )
        X = np.zeros((len(attr_names), n_total))
        X[:, 0] = model.p_pred.ravel()
        for i in range(model.n_ortho):
            X[:, 1 + i] = model.p_ortho[i].ravel()
        metas = np.array(attr_names, dtype=object).reshape(-1, 1)
        comp = Table.from_numpy(dom, X=X, metas=metas)
        comp.name = "OPLS-DA components"
        return comp

    def _create_splot_table(self):
        """Return S-Plot coordinates as a Table."""
        model = self.model
        data = self.data
        model_data = model.data_to_model_domain(data)
        Xt = model_data.X

        p_vals, pcorr_vals, t_pred = model.plot_data(Xt)
        self.splot_p = p_vals
        self.splot_pcorr = pcorr_vals
        self.splot_feature_names = [a.name for a in model.domain.attributes]

        dom = Domain(
            [ContinuousVariable("p"),
             ContinuousVariable("p(corr)")],
            metas=[StringVariable("Variable")],
        )
        X = np.column_stack((p_vals, pcorr_vals))
        metas = np.array(self.splot_feature_names, dtype=object).reshape(-1, 1)
        st = Table.from_numpy(dom, X=X, metas=metas)
        st.name = "S-Plot data"
        return st

    def _compute_biomarkers(self):
        """Identify top biomarkers by |p| > threshold."""
        if self.splot_p is None or self.splot_feature_names is None:
            return None

        # Biomarkers = variables with |p(corr)| > 0.5 (or high |p|)
        p_abs = np.abs(self.splot_p)
        pcorr_abs = np.abs(self.splot_pcorr)
        score = p_abs * pcorr_abs  # combined importance

        idx = np.argsort(score)[::-1]
        dom = Domain(
            [ContinuousVariable("p"),
             ContinuousVariable("p(corr)"),
             ContinuousVariable("Importance")],
            metas=[StringVariable("Variable")],
        )
        X = np.column_stack((
            self.splot_p[idx], self.splot_pcorr[idx], score[idx],
        ))
        metas = np.array(
            [self.splot_feature_names[i] for i in idx],
            dtype=object,
        ).reshape(-1, 1)
        bt = Table.from_numpy(dom, X=X, metas=metas)
        bt.name = "Biomarkers (S-Plot)"
        return bt

    def _draw_splot(self):
        """Draw the S-Plot in the widget."""
        self.plot_widget.clear()
        if self.splot_p is None or self.splot_pcorr is None:
            return

        self.scatter_item = pg.ScatterPlotItem(
            x=self.splot_p,
            y=self.splot_pcorr,
            pen=pg.mkPen(0.3, width=0.5),
            brush=pg.mkBrush(60, 120, 200, 180),
            size=6,
        )
        self.plot_widget.addItem(self.scatter_item)

        # Horizontal/vertical lines at 0
        self.plot_widget.addLine(x=0, pen=QColor(180, 180, 180, 120))
        self.plot_widget.addLine(y=0, pen=QColor(180, 180, 180, 120))

        # Label top/bottom biomarkers
        scores = np.abs(self.splot_p) * np.abs(self.splot_pcorr)
        top3 = np.argsort(scores)[-3:]
        label_pen = pg.mkPen(color=(40, 40, 40))
        for i in top3:
            txt = pg.TextItem(
                text=self.splot_feature_names[i],
                anchor=(0.5, 1.5),
                color=(40, 40, 40),
            )
            txt.setPos(self.splot_p[i], self.splot_pcorr[i])
            self.plot_widget.addItem(txt)


if __name__ == "__main__":  # pragma: no cover
    WidgetPreview(OWOPLSDA).run(Table("zoo"))