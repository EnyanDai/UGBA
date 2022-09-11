import numpy as np
import torch.nn.functional as F
from torch_geometric.utils import to_dense_adj,dense_to_sparse
import torch
import scipy.sparse as sp

def edge_sim_analysis(edge_index, features):
    sims = []
    for (u,v) in edge_index:
        sims.append(float(F.cosine_similarity(features[u].unsqueeze(0),features[v].unsqueeze(0))))
    sims = np.array(sims)
    # print(f"mean: {sims.mean()}, <0.1: {sum(sims<0.1)}/{sims.shape[0]}")
    return sims
def prune_unrelated_edge(args,input_edge_index,input_edge_weights,x,device):
    # x = x.to_dense()
    adj = to_dense_adj(input_edge_index,edge_attr=input_edge_weights)[0].cpu()
    input_edge_index, input_edge_weights= dense_to_sparse(adj)
    edges_index = adj.nonzero()
    # edges_index = torch.transpose(input_edge_index,0,1)
    edge_sims = F.cosine_similarity(x[input_edge_index[0]],x[input_edge_index[1]])
    # edge_sims = edge_sim_analysis(edges_index,x)
    dissim_edges_index = np.where(edge_sims.cpu()<=args.prune_thr)[0]
    # dissim_edges_index = np.where(edge_sims>=0.8)[0]
    dissim_edges = edges_index[dissim_edges_index]
    for (u,v) in dissim_edges:
        adj[u,v] = 0
    updated_edge_index,updated_edge_weights = dense_to_sparse(adj.to(device))
    return updated_edge_index,updated_edge_weights
def prune_unrelated_edge_isolated(args,input_edge_index,input_edge_weights,x,device):
    adj = to_dense_adj(input_edge_index,edge_attr=input_edge_weights)[0].cpu()
    input_edge_index, input_edge_weights= dense_to_sparse(adj)
    edges_index = adj.nonzero()
    # edges_index = torch.transpose(input_edge_index,0,1)
    # edge_sims = edge_sim_analysis(edges_index,x)
    edge_sims = F.cosine_similarity(x[input_edge_index[0]],x[input_edge_index[1]])
    dissim_edges_index = np.where(edge_sims.cpu()<=args.prune_thr)[0]
    # dissim_edges_index = np.where(edge_sims>=0.8)[0]
    dissim_edges = edges_index[dissim_edges_index]
    can_nodes = []
    for (u,v) in dissim_edges:
        adj[u,v] = 0
        # adj[v,u] = 0
        can_nodes.append(int(u))
        can_nodes.append(int(v))
    can_nodes = list(set(can_nodes))

    # adj = adj.to_sparse()
    # x = x.to_sparse()
    updated_edge_index,updated_edge_weights = dense_to_sparse(adj.to(device))
    return updated_edge_index,updated_edge_weights,can_nodes

def select_target_nodes(args,seed,model,features,edge_index,edge_weights,labels,idx_val,idx_test):
    test_ca,test_correct_index = model.test_with_correct_nodes(features,edge_index,edge_weights,labels,idx_test)
    test_correct_index = test_correct_index.tolist()
    '''select target test nodes'''
    test_correct_nodes = idx_test[test_correct_index].tolist()
    # filter out the test nodes that are not in target class
    target_class_nodes_test = [int(nid) for nid in idx_test
            if labels[nid]==args.target_class] 
    # get the target test nodes
    idx_val,idx_test = idx_val.tolist(),idx_test.tolist()
    rs = np.random.RandomState(seed)
    cand_atk_test_nodes = list(set(test_correct_nodes) - set(target_class_nodes_test))  # the test nodes not in target class is candidate atk_test_nodes
    atk_test_nodes = rs.choice(cand_atk_test_nodes, args.target_test_nodes_num)
    '''select clean test nodes'''
    cand_clean_test_nodes = list(set(idx_test) - set(atk_test_nodes))
    clean_test_nodes = rs.choice(cand_clean_test_nodes, args.clean_test_nodes_num)
    '''select poisoning nodes from unlabeled nodes (assign labels is easier than change, also we can try to select from labeled nodes)'''
    N = features.shape[0]
    cand_poi_train_nodes = list(set(idx_val)-set(atk_test_nodes)-set(clean_test_nodes))
    poison_nodes_num = int(N * args.vs_ratio)
    poi_train_nodes = rs.choice(cand_poi_train_nodes, poison_nodes_num)
    
    return atk_test_nodes, clean_test_nodes,poi_train_nodes

def normalize(mx):
    """Row-normalize sparse matrix"""
    rowsum = np.array(mx.sum(1))
    r_inv = np.power(rowsum, -1).flatten()
    r_inv[np.isinf(r_inv)] = 0.
    r_mat_inv = sp.diags(r_inv)
    mx = r_mat_inv.dot(mx)
    return mx
    
def normalize_adj(adj):
    """Symmetrically normalize adjacency matrix."""
    adj = sp.coo_matrix(adj)
    rowsum = np.array(adj.sum(1))
    d_inv_sqrt = np.power(rowsum, -0.5).flatten()
    d_inv_sqrt[np.isinf(d_inv_sqrt)] = 0.
    d_mat_inv_sqrt = sp.diags(d_inv_sqrt)
    return adj.dot(d_mat_inv_sqrt).transpose().dot(d_mat_inv_sqrt).tocsr()