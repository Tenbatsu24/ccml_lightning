from loguru import logger

import torch


def init_optims_from_config(config, model):
    if config.turn_off_norm_weight_decay:
        custom_keys_weight_decay = [
            (key, 0.0)
            for key in ["class_token", "position_embedding", "relative_position_bias_table"]
        ]

        if hasattr(model, "custom_keys_weight_decay_filter"):
            custom_keys_weight_decay.extend(
                [(key, 0.0) for key in model.custom_keys_weight_decay_filter]
            )

        params = set_weight_decay(
            model,
            config.opt.params.weight_decay,
            0.0,
            custom_keys_weight_decay=custom_keys_weight_decay,
        )
        logger.info("Turn Off Norm Weight Decay")
        for param_groups in params:
            logger.info(
                f"For param group with: {len(param_groups['params'])} params, WD: {param_groups['weight_decay']})"
            )
    else:
        params = [p for p in model.parameters() if p.requires_grad]

    if hasattr(torch.optim, config.opt.type):
        opt = getattr(torch.optim, config.opt.type)(params, **config.opt.params)
    else:
        raise NotImplementedError(f"Unknown optimizer: {config.opt.type}")

    return [opt]


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


if __name__ == "__main__":
    from ml.model.image_classification import get_model

    _custom_keys_weight_decay = [
        (key, 0.0) for key in ["class_token", "position_embedding", "relative_position_bias_table"]
    ]
    _custom_keys_weight_decay.append(("bias", 0.0))

    _model = get_model("c", "swin_tiny")(num_classes=1000)

    for _param_groups in set_weight_decay(
        _model, 2e-5, 0.0, custom_keys_weight_decay=_custom_keys_weight_decay
    ):
        print(len(_param_groups["params"]), _param_groups["weight_decay"])

    print(_model)
