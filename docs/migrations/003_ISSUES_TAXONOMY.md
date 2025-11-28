# Migration 003: Issue Taxonomy Normalization

## Problem

The `issues_decisions` table stored `category` and `subcategory` as raw text strings. This caused:

- Inconsistent data (e.g., "Prop. Div." vs "Property Division")
- Slow text-based searches
- No hierarchical relationship

## Solution

Created a self-referencing `issue_taxonomy` table with 3 levels:

```
Family Law (Level 0 - Root)
│
├── Property Division / Debt Allocation (Level 1)
│   ├── Division fairness (229 issues)
│   ├── Valuation of assets (179 issues)
│   ├── Characterization - community vs. separate (71 issues)
│   ├── Omitted assets or debts (35 issues)
│   └── Tax consequences ignored (2 issues)
│
├── Spousal Support / Maintenance (Level 1)
│   ├── Amount calculation errors (105 issues)
│   ├── Duration - temp vs. permanent (50 issues)
│   ├── Failure to consider statutory factors (7 issues)
│   └── Imputed income disputes (5 issues)
│
├── Child Support (Level 1)
│   ├── Income determination / imputation (174 issues)
│   ├── Retroactive support (41 issues)
│   ├── Deviations from standard calculation (40 issues)
│   └── Allocation of expenses (32 issues)
│
├── Parenting Plan / Custody / Visitation (Level 1)
│   ├── Residential schedule (109 issues)
│   ├── Restrictions - DV, SA, etc. (100 issues)
│   ├── Decision-making authority (70 issues)
│   └── Relocation disputes (40 issues)
│
├── Attorney Fees & Costs (Level 1)
│   └── Fee awards (171 issues)
│
├── Procedural & Evidentiary Issues (Level 1)
│   ├── Abuse of discretion (202 issues)
│   ├── Improper evidentiary rulings (120 issues)
│   ├── Denial of due process (19 issues)
│   └── Failure to enter findings/conclusions (15 issues)
│
├── Enforcement & Contempt Orders (Level 1)
│   ├── Willfulness findings (20 issues)
│   └── Sanctions (2 issues)
│
├── Jurisdiction & Venue (Level 1)
│   ├── Subject matter jurisdiction (21 issues)
│   └── Personal jurisdiction (5 issues)
│
└── Miscellaneous / Unclassified (Level 1)
    ├── Meretricious Relationship (3 issues)
    ├── ERISA and Safe Harbor Provision (3 issues)
    └── 200+ other rare subcategories
```

## Changes

| Table              | Change                                                     |
| ------------------ | ---------------------------------------------------------- |
| `issue_taxonomy`   | New table with `taxonomy_id`, `parent_id`, `name`, `level` |
| `issues_decisions` | Added `taxonomy_id` FK column                              |

## Stats

- 1 root node (Family Law)
- 9 categories
- 376 subcategories
- 2,273 issues linked

## Query Example

```sql
-- Find all Property Division issues
SELECT id.* FROM issues_decisions id
JOIN issue_taxonomy sub ON id.taxonomy_id = sub.taxonomy_id
JOIN issue_taxonomy cat ON sub.parent_id = cat.taxonomy_id
WHERE cat.name = 'Property Division / Debt Allocation';
```
