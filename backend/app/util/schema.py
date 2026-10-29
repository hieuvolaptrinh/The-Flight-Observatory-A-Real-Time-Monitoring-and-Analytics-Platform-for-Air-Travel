from typing import Optional, get_args, get_origin, Union

from pydantic._internal._model_construction import ModelMetaclass


class AllOptional(ModelMetaclass):


    def __new__(mcs, name, bases, namespace, **kwargs):
        annotations = namespace.get("__annotations__", {})
        # Thu thập annotation từ các base classes
        for base in bases:
            if hasattr(base, "__annotations__"):
                for key, value in base.__annotations__.items():
                    if key not in annotations and not key.startswith("_"):
                        annotations[key] = value


        for field_name in list(annotations):
            if field_name.startswith("_"):
                continue
            field_type = annotations[field_name]
            origin = get_origin(field_type)
            if origin is Union:
                args = get_args(field_type)
                if type(None) not in args:
                    annotations[field_name] = Optional[field_type]
            else:
                annotations[field_name] = Optional[field_type]
            if field_name not in namespace:
                namespace[field_name] = None

        namespace["__annotations__"] = annotations
        return super().__new__(mcs, name, bases, namespace, **kwargs)
