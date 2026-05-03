from torch_geometric.nn.pool import global_add_pool, global_max_pool, global_mean_pool

pooling_dict = {
    'add': global_add_pool,
    'mean': global_mean_pool,
    'max': global_max_pool
}
