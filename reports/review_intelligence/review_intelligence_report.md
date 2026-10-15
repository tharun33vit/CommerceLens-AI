# CommerceLens AI — Customer Review Intelligence Report

> **Phase 5 Intelligence Artifact**: Natural Language Processing & Customer Feedback Mining

---

## 1. Executive Summary & Processing Coverage

- **Total Source Reviews**: 99,224
- **Eligible Reviews with Text**: 42,697 (43.0% of total)
- **Reviews without Text**: 56,527
- **Processed Pilot Cohort**: 160 (0.37% of text reviews)
- **Successfully Completed**: 132
- **Failed / Errors**: 28

---

## 2. Sentiment Distribution (Processed Cohort)

| Sentiment Label | Review Count | Share (%) |
|:---|:---:|:---:|
| **positive** | 74 | 56.06% |
| **unclear** | 25 | 18.94% |
| **negative** | 21 | 15.91% |
| **mixed** | 10 | 7.58% |
| **neutral** | 2 | 1.52% |

---

## 3. Review Theme Frequency & Prevalences

| Theme Identifier | Total Occurrences | Primary Theme Count | Prevalence (%) |
|:---|:---:|:---:|:---:|
| `positive_product_experience` | 63 | 45 | 47.73% |
| `unclear` | 57 | 56 | 43.18% |
| `positive_delivery_experience` | 35 | 28 | 26.52% |
| `delivery_delay` | 13 | 12 | 9.85% |
| `poor_product_quality` | 5 | 3 | 3.79% |
| `damaged_or_defective_product` | 5 | 4 | 3.79% |
| `missing_or_wrong_item` | 4 | 4 | 3.03% |
| `positive_seller_experience` | 4 | 0 | 3.03% |
| `payment_or_pricing` | 4 | 2 | 3.03% |
| `product_not_as_described` | 3 | 2 | 2.27% |
| `return_or_refund` | 2 | 1 | 1.52% |
| `other` | 2 | 1 | 1.52% |
| `packaging_issue` | 2 | 1 | 1.52% |
| `seller_communication` | 1 | 0 | 0.76% |
| `delivery_tracking` | 1 | 1 | 0.76% |

---

## 4. Rating Proxy vs Text Sentiment Concordance

- **Total Reviews Compared**: 132
- **Concordance Rate**: **62.88%**

> [!NOTE]
> **Analytical Caveat**: The rating proxy (Scores 1–2 = negative, Score 3 = neutral, Scores 4–5 = positive) is an operational comparison baseline, not a perfect ground-truth annotation. Customers frequently award high scores while noting minor complaints, or award low scores while expressing neutral or mixed text.

---

## 5. Delivery Timeliness Cohort vs Review Sentiment

| Delivery Cohort | Reviews Analyzed | Delivery-Related Reviews | Delivery Related (%) | Negative Sentiment (%) |
|:---|:---:|:---:|:---:|:---:|
| **Late Delivery** | 1 | 1 | 100.00% | 100.00% |
| **On-Time Delivery** | 125 | 56 | 44.80% | 12.00% |

---

## 6. Analytical Guardrails & Non-Causality

> Analytical Disclaimer: Statistical correlation between delivery timeliness and review sentiment does not establish direct causation. Confounding variables such as merchant responsiveness, packaging fragility, and carrier handling quality also influence customer satisfaction.
