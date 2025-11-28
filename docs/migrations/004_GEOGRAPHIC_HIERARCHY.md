# Migration 004: Geographic Hierarchy

## Problem

Counties stored as free-text with inconsistencies:

- "King County" vs "King"
- "Benton" vs "Benton County"
- No link between county → district → state

## Solution

Created `jurisdictions` table with self-referencing hierarchy:

```
Washington (Level 0 - State)
├── Division I (Level 1 - District)
│   ├── King (Level 2 - County)
│   ├── Snohomish
│   └── ...
├── Division II
│   └── ...
└── Division III
    └── ...
```

## Changes

| Table           | Change                                                                              |
| --------------- | ----------------------------------------------------------------------------------- |
| `jurisdictions` | New table with `jurisdiction_id`, `parent_id`, `name`, `jurisdiction_type`, `level` |
| `cases`         | Added `jurisdiction_id` FK column                                                   |

## Stats

- 1 state (Washington)
- 3 districts (Division I, II, III)
- 39 counties
- 940 cases linked

## Query Example

```sql
-- Get all Division I cases with county
SELECT c.title, county.name, district.name
FROM cases c
JOIN jurisdictions county ON c.jurisdiction_id = county.jurisdiction_id
JOIN jurisdictions district ON county.parent_id = district.jurisdiction_id
WHERE district.name = 'Division I';
```
