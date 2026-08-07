from __future__ import annotations

from typing import Any

from visual_system import make_button


_INSTALLED_CLASSES: set[type[Any]] = set()


def _eligible_targets(app: Any, resource: str) -> list[Any]:
    """Return eligible targets ranked by the requested resource only."""
    active = app._active_coords()
    minimum_metal = max(0, app._safe_int(app.min_metal_queue_var, 480000))
    ranked: list[tuple[Any, int]] = []

    for target in app.targets:
        if (
            not target.enabled
            or target.blacklisted
            or target.coord in active
            or target.last_spy_at is None
        ):
            continue

        if resource == "metal":
            value = target.metal
            if value is None or value < minimum_metal:
                continue
        elif resource == "minerals":
            value = target.minerals
            if value is None:
                continue
        else:
            raise ValueError(f"Unsupported queue resource: {resource}")

        ranked.append((target, int(value)))

    ranked.sort(key=lambda item: (-item[1], item[0].coord))
    return [target for target, _ in ranked]


def install_resource_queue_modes(app_class: type[Any]) -> None:
    if app_class in _INSTALLED_CLASSES:
        return

    original_build_queue_page = app_class._build_queue_page
    original_render_queue = app_class.render_queue

    def generate_queue_by_resource(self: Any, resource: str) -> None:
        count = max(1, self._safe_int(self.queue_size_var, 45))
        targets = _eligible_targets(self, resource)
        coords = [target.coord for target in targets[:count]]
        self.db.replace_queue(coords)

        values: dict[str, Any] = {
            "queue_size": count,
            "queue_resource_mode": resource,
        }
        if resource == "metal":
            values["min_metal_for_queue"] = max(0, self._safe_int(self.min_metal_queue_var, 480000))

        self.db.set_settings(values)
        self.settings.update(values)
        self._queue_resource_mode = resource

        label = "металлу" if resource == "metal" else "минералам"
        self.logger.info("Сформирован план отправки: %s целей по %s", len(coords), label)
        self.status_var.set(f"План собран по {label} · {len(coords)} целей")
        self.render_all()

    def generate_queue_by_metal(self: Any) -> None:
        generate_queue_by_resource(self, "metal")

    def generate_queue_by_minerals(self: Any) -> None:
        generate_queue_by_resource(self, "minerals")

    def generate_queue(self: Any) -> None:
        # Keep legacy callers (refresh/import flows) deterministic: default to metal.
        generate_queue_by_resource(self, "metal")

    def build_queue_page(self: Any) -> None:
        original_build_queue_page(self)
        button = self._find_button("Сформировать") if hasattr(self, "_find_button") else None
        if button is None:
            # Base app instances do not have app_entry's helper, so search locally.
            pending = list(self.pages["queue"].winfo_children())
            while pending and button is None:
                widget = pending.pop(0)
                pending.extend(widget.winfo_children())
                try:
                    if str(widget.cget("text")) == "Сформировать":
                        button = widget
                except Exception:
                    pass
        if button is None:
            return

        button.configure(text="Собрать по металлу", command=self.generate_queue_by_metal)
        make_button(
            button.master,
            "Собрать по минералам",
            self.generate_queue_by_minerals,
            "secondary",
            size="compact",
        ).pack(side="left", padx=(6, 0), pady=(16, 0))

        # The next raid follows the built queue order, not a hidden hard-coded resource.
        try:
            section = button.master.master.master
            for widget in section.winfo_children():
                for child in widget.winfo_children():
                    try:
                        text = str(child.cget("text"))
                    except Exception:
                        continue
                    if "без галочек" in text:
                        child.configure(text="поставьте галочки для волны; без галочек «следующий» идёт сверху вниз по плану")
        except Exception:
            pass

    def render_queue(self: Any) -> None:
        original_render_queue(self)
        tree = getattr(self, "queue_tree", None)
        if tree is None:
            return
        mode = str(getattr(self, "_queue_resource_mode", self.settings.get("queue_resource_mode", "metal")))
        if mode not in {"metal", "minerals"}:
            mode = "metal"
        self._queue_resource_mode = mode
        label = "Металл" if mode == "metal" else "Минералы"
        try:
            tree.heading("score", text=f"Приоритет · {label}")
        except Exception:
            pass
        for iid in tree.get_children(""):
            values = list(tree.item(iid, "values"))
            if len(values) < 12 or not str(iid).startswith("q:"):
                continue
            try:
                item_id = int(str(iid).split(":", 1)[1])
            except ValueError:
                continue
            item = next((row for row in self.db.list_queue() if row.id == item_id), None)
            target = self.target_by_coord.get(item.coord) if item else None
            if target is None:
                continue
            value = target.metal if mode == "metal" else target.minerals
            values[11] = self._format_queue_resource(value)
            tree.item(iid, values=values)

    def _format_queue_resource(self: Any, value: int | None) -> str:
        # Match app.format_number without importing app and creating a circular dependency.
        return "—" if value is None else f"{int(value):,}".replace(",", " ")

    app_class.generate_queue_by_resource = generate_queue_by_resource
    app_class.generate_queue_by_metal = generate_queue_by_metal
    app_class.generate_queue_by_minerals = generate_queue_by_minerals
    app_class.generate_queue = generate_queue
    app_class._format_queue_resource = _format_queue_resource
    app_class._build_queue_page = build_queue_page
    app_class.render_queue = render_queue
    _INSTALLED_CLASSES.add(app_class)
