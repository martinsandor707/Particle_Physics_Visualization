/* The article's references, by citation key. The prose cites them as
 * [[cite:<key>]]; the renderer numbers them in order of first citation and
 * lists only those cited. Plain text, no markup. */

export default [
  // Calorimetry.
  { key: 'wigmans2017', text: 'R. Wigmans, Calorimetry: Energy Measurement in Particle Physics, 2nd ed., Oxford University Press, Oxford, 2017.' },
  { key: 'fabjan2003', text: 'C. W. Fabjan, F. Gianotti, Calorimetry for particle physics, Reviews of Modern Physics 75 (2003) 1243–1286.' },

  // Statistics.
  { key: 'student1908', text: 'Student, The probable error of a mean, Biometrika 6 (1908) 1–25.' },
  { key: 'fisher1921', text: 'R. A. Fisher, On the “probable error” of a coefficient of correlation deduced from a small sample, Metron 1 (1921) 3–32.' },
  { key: 'wilson1927', text: 'E. B. Wilson, Probable inference, the law of succession, and statistical inference, Journal of the American Statistical Association 22 (1927) 209–212.' },
  { key: 'wilsonhilferty1931', text: 'E. B. Wilson, M. M. Hilferty, The distribution of chi-square, Proceedings of the National Academy of Sciences of the USA 17 (1931) 684–688.' },
  { key: 'cornishfisher1938', text: 'E. A. Cornish, R. A. Fisher, Moments and cumulants in the specification of distributions, Revue de l’Institut International de Statistique 5 (1938) 307–320.' },
  { key: 'gurland1971', text: 'J. Gurland, R. C. Tripathi, A simple approximation for unbiased estimation of the standard deviation, The American Statistician 25 (4) (1971) 30–32.' },
  { key: 'cochran1977', text: 'W. G. Cochran, Sampling Techniques, 3rd ed., Wiley, New York, 1977.' },
  { key: 'quenouille1956', text: 'M. H. Quenouille, Notes on bias in estimation, Biometrika 43 (1956) 353–360.' },
  { key: 'tukey1958', text: 'J. W. Tukey, Bias and confidence in not-quite large samples (abstract), Annals of Mathematical Statistics 29 (1958) 614.' },
  { key: 'efron1979', text: 'B. Efron, Bootstrap methods: another look at the jackknife, Annals of Statistics 7 (1979) 1–26.' },
  { key: 'davison1997', text: 'A. C. Davison, D. V. Hinkley, Bootstrap Methods and their Application, Cambridge University Press, Cambridge, 1997.' },
  { key: 'freedman1981', text: 'D. Freedman, P. Diaconis, On the histogram as a density estimator: L2 theory, Zeitschrift für Wahrscheinlichkeitstheorie und verwandte Gebiete 57 (1981) 453–476.' },
  { key: 'silverman1986', text: 'B. W. Silverman, Density Estimation for Statistics and Data Analysis, Chapman & Hall, London, 1986.' },
  { key: 'wand1995', text: 'M. P. Wand, M. C. Jones, Kernel Smoothing, Chapman & Hall, London, 1995.' },
  { key: 'press1992', text: 'W. H. Press, S. A. Teukolsky, W. T. Vetterling, B. P. Flannery, Numerical Recipes in C, 2nd ed., Cambridge University Press, Cambridge, 1992.' },

  // Directional statistics.
  { key: 'rayleigh1880', text: 'Lord Rayleigh, On the resultant of a large number of vibrations of the same pitch and of arbitrary phase, Philosophical Magazine 10 (1880) 73–78.' },
  { key: 'mardia1976', text: 'K. V. Mardia, Linear-circular correlation coefficients and rhythmometry, Biometrika 63 (1976) 403–405.' },
  { key: 'mardia2000', text: 'K. V. Mardia, P. E. Jupp, Directional Statistics, Wiley, Chichester, 2000.' },
  { key: 'jammalamadaka2001', text: 'S. R. Jammalamadaka, A. SenGupta, Topics in Circular Statistics, World Scientific, Singapore, 2001.' },

  // Explainability and models.
  { key: 'selvaraju2017', text: 'R. R. Selvaraju, M. Cogswell, A. Das, R. Vedantam, D. Parikh, D. Batra, Grad-CAM: visual explanations from deep networks via gradient-based localization, Proceedings of the IEEE International Conference on Computer Vision (2017) 618–626.' },
  { key: 'zheng2022', text: 'Q. Zheng, Z. Wang, J. Zhou, J. Lu, Shap-CAM: visual explanations for convolutional neural networks based on Shapley value, Computer Vision – ECCV 2022, Lecture Notes in Computer Science, Springer, Cham, 2022.' },
  { key: 'chen2016', text: 'T. Chen, C. Guestrin, XGBoost: a scalable tree boosting system, Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining (2016) 785–794.' },
  { key: 'breiman1984', text: 'L. Breiman, J. H. Friedman, R. A. Olshen, C. J. Stone, Classification and Regression Trees, Wadsworth, Belmont, CA, 1984.' },
  { key: 'craven1996', text: 'M. W. Craven, J. W. Shavlik, Extracting tree-structured representations of trained networks, Advances in Neural Information Processing Systems 8 (1996) 24–30.' },

  // Visualisation and colour.
  { key: 'tufte2001', text: 'E. R. Tufte, The Visual Display of Quantitative Information, 2nd ed., Graphics Press, Cheshire, CT, 2001.' },
  { key: 'cleveland1984', text: 'W. S. Cleveland, R. McGill, Graphical perception: theory, experimentation, and application to the development of graphical methods, Journal of the American Statistical Association 79 (1984) 531–554.' },
  { key: 'munzner2014', text: 'T. Munzner, Visualization Analysis and Design, CRC Press, Boca Raton, FL, 2014.' },
  { key: 'westover1990', text: 'L. Westover, Footprint evaluation for volume rendering, Computer Graphics (Proceedings of SIGGRAPH ’90) 24 (4) (1990) 367–376.' },
  { key: 'borland2007', text: 'D. Borland, R. M. Taylor II, Rainbow color map (still) considered harmful, IEEE Computer Graphics and Applications 27 (2) (2007) 14–17.' },
  { key: 'crameri2020', text: 'F. Crameri, G. E. Shephard, P. J. Heron, The misuse of colour in science communication, Nature Communications 11 (2020) 5444.' },
  { key: 'nunez2018', text: 'J. R. Nuñez, C. R. Anderton, R. S. Renslow, Optimizing colormaps with consideration for color vision deficiency to enable accurate interpretation of scientific data, PLoS ONE 13 (7) (2018) e0199239.' },
  { key: 'harrower2003', text: 'M. Harrower, C. A. Brewer, ColorBrewer.org: an online tool for selecting colour schemes for maps, The Cartographic Journal 40 (1) (2003) 27–37.' },
  { key: 'mikhailov2019', text: 'A. Mikhailov, Turbo, an improved rainbow colormap for visualization, Google AI Blog, 2019.' },
  { key: 'wcag21', text: 'W3C, Web Content Accessibility Guidelines (WCAG) 2.1, W3C Recommendation, 2018.' },
  { key: 'mathmlcore', text: 'W3C, MathML Core, W3C technical report, https://www.w3.org/TR/mathml-core/.' },

  // Systems.
  { key: 'raasveldt2019', text: 'M. Raasveldt, H. Mühleisen, DuckDB: an embeddable analytical database, Proceedings of the 2019 International Conference on Management of Data (SIGMOD ’19) (2019) 1981–1984.' },
  { key: 'postgresql', text: 'The PostgreSQL Global Development Group, PostgreSQL Documentation: Parallel Plans; Resource Consumption, https://www.postgresql.org/docs/current/.' },
  { key: 'parquet', text: 'The Apache Software Foundation, Apache Parquet file format, https://parquet.apache.org/docs/file-format/.' },
  { key: 'rfc8878', text: 'Y. Collet, M. Kucherawy, Zstandard compression and the ‘application/zstd’ media type, RFC 8878, IETF, 2021.' },
  { key: 'li2018', text: 'D. Li, H. Mei, Y. Shen, S. Su, W. Zhang, J. Wang, M. Zu, W. Chen, ECharts: a declarative framework for rapid construction of web-based visualization, Visual Informatics 2 (2) (2018) 136–146.' },
  { key: 'fastapi', text: 'S. Ramírez, FastAPI, https://fastapi.tiangolo.com/.' },
];
