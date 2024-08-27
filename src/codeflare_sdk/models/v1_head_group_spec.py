import pprint

import six


class V1HeadGroupSpec(object):  # pragma: no cover
    openapi_types = {
        "serviceType": "str",
        "headService": "str",
        "enableIngress": "bool",
        "rayStartParams": "Dict[str, str]",
        "template": "V1PodTemplateSpec",
    }

    attribute_map = {
        "serviceType": "serviceType",
        "headService": "headService",
        "enableIngress": "enableIngress",
        "rayStartParams": "rayStartParams",
        "template": "template",
    }

    def __init__(
        self,
        serviceType=None,
        headService=None,
        enableIngress=None,
        rayStartParams=None,
        template=None,
    ):
        self._serviceType = None
        self._headService = None
        self._enableIngress = None
        self._rayStartParams = None
        self._template = None

        if serviceType is not None:
            self._serviceType = serviceType
        if headService is not None:
            self._headService = headService
        if enableIngress is not None:
            self._enableIngress = enableIngress
        if rayStartParams is not None:
            self._rayStartParams = rayStartParams
        if template is not None:
            self._template = template

    @property
    def serviceType(self):
        return self._serviceType

    @serviceType.setter
    def serviceType(self, serviceType):
        self._serviceType = serviceType

    @property
    def headService(self):
        return self._headService

    @headService.setter
    def headService(self, headService):
        self._headService = headService

    @property
    def enableIngress(self):
        return self._enableIngress

    @enableIngress.setter
    def enableIngress(self, enableIngress):
        self._enableIngress = enableIngress

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
        if not isinstance(other, V1HeadGroupSpec):
            return False

        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        if not isinstance(other, V1HeadGroupSpec):
            return True

        return self.to_dict() != other.to_dict()
