import pprint

import six


class V1ScaleStrategy(object):  # pragma: no cover
    openapi_types = {"workersToDelete": "List[str]"}

    attribute_map = {
        "workersToDelete": "workersToDelete",
    }

    def __init__(self, workersToDelete=None):
        self._workersToDelete = None

        if workersToDelete is not None:
            self._workersToDelete = workersToDelete

    @property
    def workersToDelete(self):
        return self._workersToDelete

    @workersToDelete.setter
    def workersToDelete(self, workersToDelete):
        self._workersToDelete = workersToDelete

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
        if not isinstance(other, V1ScaleStrategy):
            return False

        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        if not isinstance(other, V1ScaleStrategy):
            return True

        return self.to_dict() != other.to_dict()
