import pprint

import six


class V1WorkerGroupSpec(object):  # pragma: no cover
    openapi_types = {
        "groupName": "str",
        "replicas": "int32",
        "minReplicas": "int32",
        "maxReplicas": "int32",
        "rayStartParams": "V1RayStartParams",
        "template": "V1PodTemplateSpec",
        "scaleStrategy": "V1ScaleStrategy",
        "numOfHosts": "int32",
    }

    attribute_map = {
        "groupName": "groupName",
        "replicas": "replicas",
        "minReplicas": "minReplicas",
        "maxReplicas": "maxReplicas",
        "rayStartParams": "rayStartParams",
        "template": "template",
        "scaleStrategy": "scaleStrategy",
        "numOfHosts": "numOfHosts",
    }

    def __init__(
        self,
        groupName=None,
        replicas=None,
        minReplicas=None,
        maxReplicas=None,
        rayStartParams=None,
        template=None,
        scaleStrategy=None,
        numOfHosts=None,
    ):
        self._groupName = None
        self._replicas = None
        self._minReplicas = None
        self._maxReplicas = None
        self._rayStartParams = None
        self._template = None
        self._scaleStrategy = None
        self._numOfHosts = None

        if groupName is not None:
            self._groupName = groupName
        if replicas is not None:
            self._replicas = replicas
        if minReplicas is not None:
            self._minReplicas = minReplicas
        if maxReplicas is not None:
            self._maxReplicas = maxReplicas
        if rayStartParams is not None:
            self._rayStartParams = rayStartParams
        if template is not None:
            self._template = template
        if scaleStrategy is not None:
            self._scaleStrategy = scaleStrategy
        if numOfHosts is not None:
            self._numOfHosts = numOfHosts

    @property
    def groupName(self):
        return self._groupName

    @groupName.setter
    def groupName(self, groupName):
        self._groupName = groupName

    @property
    def replicas(self):
        return self._replicas

    @replicas.setter
    def replicas(self, replicas):
        self._replicas = replicas

    @property
    def minReplicas(self):
        return self._minReplicas

    @minReplicas.setter
    def minReplicas(self, minReplicas):
        self._minReplicas = minReplicas

    @property
    def maxReplicas(self):
        return self._maxReplicas

    @maxReplicas.setter
    def maxReplicas(self, maxReplicas):
        self._maxReplicas = maxReplicas

    @property
    def rayStartParams(self):
        return self._rayStartParams

    @rayStartParams.setter
    def rayStartParams(self, rayStartParams):
        self._rayStartParams = rayStartParams

    @property
    def template(self):
        return self._template

    @template.setter
    def template(self, template):
        self._template = template

    @property
    def scaleStrategy(self):
        return self._scaleStrategy

    @scaleStrategy.setter
    def scaleStrategy(self, scaleStrategy):
        self._scaleStrategy = scaleStrategy

    @property
    def numOfHosts(self):
        return self._numOfHosts

    @numOfHosts.setter
    def numOfHosts(self, numOfHosts):
        self._numOfHosts = numOfHosts

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
        if not isinstance(other, V1WorkerGroupSpec):
            return False

        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        if not isinstance(other, V1WorkerGroupSpec):
            return True

        return self.to_dict() != other.to_dict()
