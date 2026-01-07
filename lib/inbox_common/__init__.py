# -*- coding: utf-8 -*-
# lib/inbox_common/__init__.py

from .paths import (
    resolve_inbox_root,
    user_root,
    ensure_user_dirs,
    items_db_path,
    last_viewed_db_path,
    resolve_file_path,
    thumbs_dir_for_item,
    preview_dir_for_item,
)

from .items_db import (
    ensure_items_db,
    load_items_df,
    load_items_page,
    count_items,
    update_item_tag_single,
    update_item_note,
    fetch_item_by_id,
)

from .last_viewed import (
    ensure_last_viewed_db,
    touch_last_viewed,
    load_last_viewed_map,
)

from .delete_ops import (
    delete_item,
    delete_items,
)
