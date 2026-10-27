"""The XGBoost model analysis: the notebooks' E1-E5, computed in the service.

The repository ships the regressors the ``XGBoost-Reg-*`` notebooks trained -
one momentum and one angle model per species and seed, 52 v3 event features
each - and every aggregate experiment is the file one of them was trained on.
Instead of shipping precomputed figures, the service reproduces the notebooks
on the experiment's own event table, once, in the background, and stores the
results beside it:

* the 80/20 split of ``train_test_split(test_size=0.2, random_state=42)`` and
  the shipped models' predictions on its 20 % validation rows (E2, prediction
  against truth);
* E1, the notebook's five-fold cross-validation, by refitting each fold with
  the notebook's hyperparameters;
* E3, the notebook's 2,000-row 99 : 1 sample thresholded at 2 GeV;
* E4, the depth-3 surrogate tree fitted to the booster's own predictions;
* E5, the booster's gain importances, and each refitted fold's.

One module per responsibility: ``discovery`` finds the models, ``pairing``
matches an experiment to its species and seed, ``analysis`` computes (numpy,
pandas, xgboost, scikit-learn; no database), ``store`` owns the tables and the
staleness stamp, ``jobs`` runs one analysis at a time on its own worker, and
``views`` turns the stored tables into the payloads of ``GET /api/xgboost``.
"""
