# Migration 003: Issue Taxonomy Normalization

## Problem

The `issues_decisions` table stored `category` and `subcategory` as raw text strings. This caused:

- Inconsistent data (e.g., "Prop. Div." vs "Property Division")
- Slow text-based searches
- No hierarchical relationship

## Solution

Created a self-referencing `issue_taxonomy` table with 3 levels:

```
Family Law (Level 0)
├── Property Division / Debt Allocation (Level 1)
│   ├── Division fairness (Level 2)
│   ├── Valuation of assets (Level 2)
│   └── ...
├── Child Support (Level 1)
│   └── ...
└── ...
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
