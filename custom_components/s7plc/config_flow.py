def _edit_schema_sensor(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    for key, sel in [
        (CONF_DEVICE_CLASS, _device_selector_by_type(CONF_SENSORS)),
        (CONF_UNIT_OF_MEASUREMENT, selector.TextSelector()),
        (CONF_VALUE_MULTIPLIER, value_multiplier_selector),
        (CONF_MIN_VALUE, number_value_selector),
        (CONF_MAX_VALUE, number_value_selector),
        (CONF_SCALE_RAW_MIN, scale_value_selector),
        (CONF_SCALE_RAW_MAX, scale_value_selector),
        (CONF_STATE_CLASS, state_class_selector),
        (CONF_REAL_PRECISION, real_precision_selector),
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AVAILABILITY_ADDRESS, selector.TextSelector()),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    d[
        vol.Optional(
            CONF_AVAILABILITY_INVERT,
            default=bool(item.get(CONF_AVAILABILITY_INVERT, False)),
        )
    ] = selector.BooleanSelector()
    return vol.Schema(d)


def _edit_schema_binary_sensor(flow, item: dict[str, Any]) -> vol.Schema:
    d: dict[Any, Any] = {
        vol.Required(
            CONF_ADDRESS, default=item.get(CONF_ADDRESS, "")
        ): selector.TextSelector(),
        vol.Optional(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): selector.TextSelector(),
    }
    k, v = flow._optional_field(
        CONF_DEVICE_CLASS, item, _device_selector_by_type(CONF_BINARY_SENSORS)
    )
    d[k] = v
    d[vol.Optional(CONF_INVERT_STATE, default=item.get(CONF_INVERT_STATE, False))] = (
        selector.BooleanSelector()
    )
    for key, sel in [
        (CONF_SCAN_INTERVAL, scan_interval_selector),
        (CONF_AVAILABILITY_ADDRESS, selector.TextSelector()),
        (CONF_AREA, flow._get_area_selector()),
    ]:
        k, v = flow._optional_field(key, item, sel)
        d[k] = v
    d[
        vol.Optional(
            CONF_AVAILABILITY_INVERT,
            default=bool(item.get(CONF_AVAILABILITY_INVERT, False)),
        )
    ] = selector.BooleanSelector()
    return vol.Schema(d)
