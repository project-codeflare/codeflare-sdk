import pprint

import six


class V1RayCluster(object):  # pragma: no cover
    openapi_types = {
        "apiVersion": "str",
        "kind": "str",
        "metadata": "V1ObjectMeta",
        "spec": "V1RayClusterSpec",
    }

    attribute_map = {
        "apiVersion": "apiVersion",
        "kind": "kind",
        "metadata": "metadata",
        "spec": "spec",
    }

    def __init__(self, apiVersion=None, kind=None, metadata=None, spec=None):
        self._apiVersion = None
        self._kind = None
        self._metadata = None
        self._spec = None

        if apiVersion is not None:
            self._apiVersion = apiVersion
        if kind is not None:
            self._kind = kind
        if metadata is not None:
            self._metadata = metadata
        if spec is not None:
            self._spec = spec

    @property
    def apiVersion(self):
        return self._apiVersion

    @apiVersion.setter
    def apiVersion(self, apiVersion):
        self._apiVersion = apiVersion

    @property
    def kind(self):
        return self._kind

    @kind.setter
    def kind(self, kind):
        self._kind = kind

    @property
    def metadata(self):
        return self._metadata

    @metadata.setter
    def metadata(self, metadata):
        self._metadata = metadata

    @property
    def spec(self):
        return self._spec

    @spec.setter
    def spec(self, spec):
        self._spec = spec

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
        if not isinstance(other, V1RayCluster):
            return False

        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        if not isinstance(other, V1RayCluster):
            return True

        return self.to_dict() != other.to_dict()
