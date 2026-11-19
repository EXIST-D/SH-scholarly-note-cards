# A Lightweight Landslide Susceptibility Model for Mountain Roads

<!-- FICTIONAL EXAMPLE written for this Skill's documentation and tests. The study, data and numbers do not exist. -->

## Abstract

We build a landslide susceptibility model for a 310 km mountain road corridor using a random forest on eight terrain and rainfall features. Evaluated with spatial cross-validation, the model reaches an AUC of 0.87, compared with 0.81 for logistic regression. Slope angle and 30-day antecedent rainfall are the most important predictors. The model should be applied only to regions with similar geology.

## 1 Introduction

Landslides repeatedly close mountain roads and cause economic losses [1]. Statistical susceptibility models are cheap to run, but most published models are validated with random splits, which can overstate skill because nearby samples are spatially correlated [2,3]. We therefore ask whether a compact model trained on freely available layers still ranks susceptible road sections well under spatial validation.

## 2 Study Area and Data

The corridor crosses sedimentary and metamorphic terrain between 800 m and 3,200 m elevation. The landslide inventory contains 1,284 mapped landslides from 2010 to 2020; inventories before 2015 were compiled from road maintenance logs and are known to miss small events. Terrain features were derived from a 10 m digital elevation model. Daily rainfall comes from 12 gauges.

## 3 Method

We train a random forest with 500 trees and a maximum depth of 12 on eight features: slope angle, aspect, curvature, distance to faults, lithology class, 7-day rainfall, 30-day antecedent rainfall and land cover. Non-landslide points are sampled at random at a ratio of 1:1. Folds are 5 spatial blocks of 20 km. We assume that the relationship between rainfall and slope failure is stationary over the study period.

## 4 Results

The random forest reaches an AUC of 0.85 in spatial cross-validation and a precision of 0.55 in the top 10% of ranked cells, while logistic regression reaches 0.81 (Table 1). Slope angle contributes most to the model, followed by 30-day antecedent rainfall. Removing the rainfall features lowers AUC by 0.06. Performance may drop in the two northern blocks, where few landslides are recorded.

Table 1. Model performance under 5-fold spatial cross-validation.

| Model | AUC | Precision at 10% |
|---|---|---|
| Logistic regression | 0.81 | 0.42 |
| Random forest | 0.87 | 0.55 |

## 5 Discussion

The gain over logistic regression suggests that non-linear interactions between slope and rainfall matter. The results are limited to one corridor and to the sedimentary and metamorphic lithologies it contains, so transfer to other regions is untested. Incomplete inventories before 2015 probably bias the model towards larger landslides. Rainfall is interpolated from only 12 gauges, which cannot resolve convective storms.

## 6 Conclusion

A compact random forest ranks landslide-prone road sections better than logistic regression under spatial validation. We plan to test the model in a second mountain region and to add satellite rainfall estimates.

## References

[1] Author A. (2015). Landslides and road networks. Journal of Imaginary Hazards, 3, 1-12.

[2] Author B. (2016). Spatial cross-validation in susceptibility mapping. Journal of Imaginary Hazards, 5, 13-30.
