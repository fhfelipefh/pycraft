def resolve_pick_block_slot(hotbar_indices, target_block_index, current_slot):
    """Finds target_block_index in hotbar_indices, or assigns it to current_slot."""
    if target_block_index in hotbar_indices:
        return hotbar_indices.index(target_block_index), hotbar_indices
    new_hotbar = list(hotbar_indices)
    new_hotbar[current_slot] = target_block_index
    return current_slot, new_hotbar


def approach_value(current, target, max_delta):
    if current < target:
        return min(target, current + max_delta)
    if current > target:
        return max(target, current - max_delta)
    return target
