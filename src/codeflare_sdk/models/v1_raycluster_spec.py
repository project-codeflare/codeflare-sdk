import pprint

import six


class V1RayClusterSpec(object):  # pragma: no cover
    openapi_types = {
        "suspend": "bool",
        "autoscalerOptions": "V1AutoScalerOptions",
        "headServiceAnnotations": "Dict[str:str]",
        "enableInTreeAutoscaling": "bool",
        "headGroupSpec": "V1HeadGroupSpec",
        "rayVersion": "str",
        "workerGroupSpecs": "List[V1WorkerGroupSpec]",
    }

    attribute_map = {
        "suspend": "suspend",
        "autoscalerOptions": "autoscalerOptions",
        "headServiceAnnotations": "headServiceAnnotations",
        "enableInTreeAutoscaling": "enableInTreeAutoscaling",
        "headGroupSpec": "headGroupSpec",
        "rayVersion": "rayVersion",
        "workerGroupSpecs": "workerGroupSpecs",
    }

    def __init__(
        self,
        suspend=None,
        autoscalerOptions=None,
        headServiceAnnotations=None,
        enableInTreeAutoscaling=None,
        headGroupSpec=None,
        rayVersion=None,
        workerGroupSpecs=None,
    ):
        self._suspend = None
        self._autoscalerOptions = None
        self._headServiceAnnotations = None
        self._enableInTreeAutoscaling = None
        self._headGroupSpec = None
        self._rayVersion = None
        self._workerGroupSpecs = None

        if suspend is not None:
            self._suspend = suspend
        if autoscalerOptions is not None:
            self._autoscalerOptions = autoscalerOptions
        if headServiceAnnotations is not None:
            self._headServiceAnnotations = headServiceAnnotations
        if enableInTreeAutoscaling is not None:
            self._enableInTreeAutoscaling = enableInTreeAutoscaling
        if headGroupSpec is not None:
            self._headGroupSpec = headGroupSpec
        if rayVersion is not None:
            self._rayVersion = rayVersion
        if workerGroupSpecs is not None:
            self._workerGroupSpecs = workerGroupSpecs

    @property
    def suspend(self):
        return self._suspend

    @suspend.setter
    def suspend(self, suspend):
        self._suspend = suspend

    @property
    def autoscalerOptions(self):
        return self._autoscalerOptions

    @autoscalerOptions.setter
    def autoscalerOptions(self, autoscalerOptions):
        self._autoscalerOptions = autoscalerOptions

    @property
    def headServiceAnnotations(self):
        return self._headServiceAnnotations

    @headServiceAnnotations.setter
    def headServiceAnnotations(self, headServiceAnnotations):
        self._headServiceAnnotations = headServiceAnnotations

    @property
    def enableInTreeAutoscaling(self):
        return self._enableInTreeAutoscaling

    @enableInTreeAutoscaling.setter
    def enableInTreeAutoscaling(self, enableInTreeAutoscaling):
        self._enableInTreeAutoscaling = enableInTreeAutoscaling

    @property
    def headGroupSpec(self):
        return self._headGroupSpec

    @headGroupSpec.setter
    def headGroupSpec(self, headGroupSpec):
        self._headGroupSpec = headGroupSpec

    @property
    def rayVersion(self):
        return self._rayVersion

    @rayVersion.setter
    def rayVersion(self, rayVersion):
        self._rayVersion = rayVersion

    @property
    def workerGroupSpecs(self):
        return self._workerGroupSpecs

    @workerGroupSpecs.setter
    def workerGroupSpecs(self, workerGroupSpecs):
        self._workerGroupSpecs = workerGroupSpecs

    def to_dict(self):
        """Returns the model properties as a dict"""
        result = {}

        for attr, _ in six.iteritems(self.openapi_types):
            value = getattr(self, attr)
            if isinstance(value, list):
                result[attr] = list(
                    map(lambda x: x.to_dict() if hasattr(x, "to_dict") else x, value)
                )
            elif hasattr(value, "to_dict"):
                result[attr] = value.to_dict()
            elif isinstance(value, dict):
                result[attr] = dict(
                    map(
                        lambda item: (item[0], item[1].to_dict())
                        if hasattr(item[1], "to_dict")
                        else item,
                        value.items(),
                    )
                )
            else:
                result[attr] = value

        return result

    def to_str(self):
        """Returns the string representation of the model"""
        return pprint.pformat(self.to_dict())

    def __repr__(self):
        """For `print` and `pprint`"""
        return self.to_str()

    def __eq__(self, other):
        """Returns true if both objects are equal"""
        if not isinstance(other, V1RayClusterSpec):
            return False

        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        if not isinstance(other, V1RayClusterSpec):
            return True

        return self.to_dict() != other.to_dict()
