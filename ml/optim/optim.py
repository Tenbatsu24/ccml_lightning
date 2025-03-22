import torch

import ml.optim.custom.optim as custom_optim


def init_optims_from_config(config, model):
    if config.opt.turn_off_norm_weight_decay:
        custom_keys_weight_decay = [
            (key, 0.) for key in ["class_token", "position_embedding", "relative_position_bias_table"]
        ]
        if hasattr(config.opt, 'custom_keys_weight_decay_filter'):
            custom_keys_weight_decay.extend([
                (key, 0.) for key in config.custom_keys_weight_decay_filter
            ])
        params = set_weight_decay(
            model, config.opt.params.weight_decay, 0., custom_keys_weight_decay=custom_keys_weight_decay
        )
        print('Turn Off Norm Weight Decay')
        for param_groups in params:
            print(len(param_groups['params']), param_groups['weight_decay'])
    else:
        params = [p for p in model.parameters() if p.requires_grad]

    if hasattr(torch.optim, config.opt.name):
        base_optim = opt = getattr(torch.optim, config.opt.name)(
            params,
            **config.opt.params
        )
    elif hasattr(custom_optim, config.opt.name) and config.opt.name != 'SAM':
        base_optim = opt = getattr(custom_optim, config.opt.name)(
            params,
            **config.opt.params
        )
    elif hasattr(custom_optim, config.opt.name):
        base_optim_cls = getattr(torch.optim, config.opt.name)
        config.opt.params.base_optim = base_optim_cls

        opt = getattr(custom_optim, config.opt.name)(
            params,
            **config.opt.params
        )

        base_optim = opt.base_optimizer
    else:
        raise NotImplementedError(f'Unknown optimizer: {config.opt.type}')

    lr_scheduler = []
    for s, p, i in zip(config.lr_scheduler.name, config.lr_scheduler.params, config.lr_scheduler.interval):
        if hasattr(torch.optim.lr_scheduler, s):
            lr_scheduler.append(
                {
                    'scheduler': getattr(torch.optim.lr_scheduler, s)(base_optim, **p),
                    'interval': i,
                    'frequency': 1
                }
            )
        else:
            from .lr_scheduler import get_cosine_schedule_with_warmup
            lr_scheduler.append(
                {
                    'scheduler': get_cosine_schedule_with_warmup(base_optim, **p),
                    'interval': i,
                    'frequency': 1
                }
            )
    return [opt], lr_scheduler


def set_weight_decay(
        model,
        weight_decay,
        norm_weight_decay=None,
        norm_classes=None,
        custom_keys_weight_decay=None,
):
    if not norm_classes:
        norm_classes = [
            torch.nn.modules.batchnorm._BatchNorm,
            torch.nn.LayerNorm,
            torch.nn.GroupNorm,
            torch.nn.modules.instancenorm._InstanceNorm,
            torch.nn.LocalResponseNorm,
        ]
    norm_classes = tuple(norm_classes)

    params = {
        "other": [],
        "norm": [],
    }
    params_weight_decay = {
        "other": weight_decay,
        "norm": norm_weight_decay,
    }
    custom_keys = []
    if custom_keys_weight_decay is not None:
        for key, weight_decay in custom_keys_weight_decay:
            params[key] = []
            params_weight_decay[key] = weight_decay
            custom_keys.append(key)

    def _add_params(module, prefix=""):
        for name, p in module.named_parameters(recurse=False):
            if not p.requires_grad:
                continue
            is_custom_key = False
            for key in custom_keys:
                target_name = f"{prefix}.{name}" if prefix != "" and "." in key else name
                if key == target_name:
                    params[key].append(p)
                    is_custom_key = True
                    break
            if not is_custom_key:
                if norm_weight_decay is not None and isinstance(module, norm_classes):
                    params["norm"].append(p)
                else:
                    params["other"].append(p)

        for child_name, child_module in module.named_children():
            child_prefix = f"{prefix}.{child_name}" if prefix != "" else child_name
            _add_params(child_module, prefix=child_prefix)

    _add_params(model)

    param_groups = []
    for key in params:
        if len(params[key]) > 0:
            param_groups.append({"params": params[key], "weight_decay": params_weight_decay[key]})
    return param_groups


if __name__ == '__main__':
    from ml.model import get_model

    _custom_keys_weight_decay = [
        (key, 0.) for key in
        ["class_token", "position_embedding", "relative_position_bias_table", "pos_embed", "cls_token"]
    ]

    _model = get_model('cifar_gfnet')(num_classes=1000)

    for _param_groups in set_weight_decay(_model, 2e-5, 0., custom_keys_weight_decay=_custom_keys_weight_decay):
        print(len(_param_groups['params']), _param_groups['weight_decay'])

    print(_model)
