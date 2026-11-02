"""Plot area reservations, crop rotation, required tasks and harvest history."""
import from typing { cast }
node Plot {
    has name: str,
        area: int;
}
node Crop {
    has name: str,
        family: str;
}
node Planting {
    has area: int,
        status: str = "growing";
}
node Task {
    has name: str,
        done: bool = False;
}
node Harvest {
    has quantity: int;
}
edge HasPlanting {}
edge CropRef {}
edge HasTask {}
edge HasHarvest {}
def _plot(p: object) -> bool {
    return isinstance(p, Plot) and jid(p) in [jid(x) for x in [root-->[?:Plot]]];
}
def _planting(p: object) -> bool {
    return isinstance(p, Planting)
        and any(_plot(x) for x in [p<-:HasPlanting:<-[?:Plot]]);
}
walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Plot]] {
            report {"ok": True};
            return;
        }
        here ++> Plot(name="North bed", area=10 + self.seed % 3);
        here ++> Plot(name="South bed", area=6);
        here ++> Crop(name="Tomato", family="nightshade");
        here ++> Crop(name="Bean", family="legume");
        report {"ok": True};
    }
}

walker GardenBoard {
    has plots: list[dict] = [],
        crops: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Plot]];
        visit [-->[?:Crop]];
    }
    can crop with Crop entry {
        self.crops.append({"id": jid(here), "name": here.name, "family": here.family});
    }
    can plot with Plot entry {
        self.plots.append(
            {
                "id": jid(here),
                "name": here.name,
                "area": here.area,
                "plantings": [
                    {
                        "id": jid(p),
                        "area": p.area,
                        "status": p.status,
                        "crop": [p->:CropRef:->[?:Crop]][0].name,
                        "tasks": [
                            {"id": jid(t), "name": t.name, "done": t.done}
                            for t in [p->:HasTask:->[?:Task]]
                        ],
                        "harvest": sum(
                            h.quantity for h in [p->:HasHarvest:->[?:Harvest]]
                        )
                    } for p in [here->:HasPlanting:->[?:Planting]]
                ]
            }
        );
    }
    can finish with Root exit {
        report {"plots": self.plots, "crops": self.crops};
    }
}

walker PlantCrop {
    has plot_id: str,
        crop_id: str,
        area: int;

    can plant with Root entry {
        plot = jobj(self.plot_id);
        crop = jobj(self.crop_id);
        if not _plot(plot)
            or not isinstance(crop, Crop)
            or self.crop_id not in [jid(x) for x in [-->[?:Crop]]] {
            report {"ok": False, "error": "Plot or crop is not available"};
            return;
        }
        plot = cast(Plot, plot);
        rows = [plot->:HasPlanting:->[?:Planting]];
        completed = [
            p
            for p in rows
            if p.status == "harvested"
        ];
        if self.area < 1
            or self.area
                + sum(
                    p.area
                    for p in rows
                    if p.status == "growing"
                )
                > plot.area {
            report {"ok": False, "error": "Planting exceeds available plot area"};
            return;
        }
        if completed
            and [completed[-1]->:CropRef:->[?:Crop]][0].family == crop.family {
            report {
                "ok": False,
                "error": "Rotate to a different crop family after harvest"
            };
            return;
        }
        p = plot +>:HasPlanting:+> Planting(area=self.area);
        p +>:CropRef:+> crop;
        for name in ["Water", "Inspect"] {
            p +>:HasTask:+> Task(name=name);
        }
        report {"ok": True, "planting_id": jid(p)};
    }
}

walker CompleteTask {
    has task_id: str;

    can complete with Root entry {
        t = jobj(self.task_id);
        if not isinstance(t, Task)
            or not any(_planting(p) for p in [t<-:HasTask:<-[?:Planting]]) {
            report {"ok": False, "error": "Task is not available"};
            return;
        }
        if t.done {
            report {"ok": False, "error": "Task is already completed"};
            return;
        }
        t.done = True;
        report {"ok": True};
    }
}

walker HarvestPlanting {
    has planting_id: str,
        quantity: int;

    can harvest with Root entry {
        p = jobj(self.planting_id);
        if not _planting(p) {
            report {"ok": False, "error": "Planting is not available"};
            return;
        }
        p = cast(Planting, p);
        if p.status != "growing"
            or self.quantity < 1
            or not all(t.done for t in [p->:HasTask:->[?:Task]]) {
            report {
                "ok": False,
                "error": "Complete every growing task before a positive harvest"
            };
            return;
        }
        p +>:HasHarvest:+> Harvest(quantity=self.quantity);
        p.status = "harvested";
        report {"ok": True};
    }
}
