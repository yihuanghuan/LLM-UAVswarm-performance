# Formal-equivalent runtime demos

This root is exclusively non-formal. The worker reconstructs a registered trial
and calls the same experiment backend function used by its formal adapter. It
does not import or call the global campaign launcher, cursor, or suite journal.

All retained manifests use `dataset_class=engineering_validation`,
`accepted_formal_result=false`, `result_notice=NOT_FORMAL_RESULT`, and
`formal_cursor_consumed=false`.

The Campaign v1 byte manifest is captured before the first demo and checked
before and after every demo. Existing demo directories are never overwritten.
