import pprint

import six


class V1AutoScalerOptions(object):  # pragma: no cover
    openapi_types = {
        "resources": "V1ResourceRequirements",
        "image": "str",
        "imagePullPolicy": "str",
        "securityContext": "V1SecurityContext",
        "idleTimeoutSeconds": "int32",
        "upscalingMode": "str",
        "env": "List[V1EnvVar]",
        "envFrom": "List[V1EnvFromSource]",
        "volumeMounts": "List[V1VolumeMount]",
    }

    attribute_map = {
        "resources": "resources",
        "image": "image",
        "imagePullPolicy": "imagePullPolicy",
        "securityContext": "securityContext",
        "idleTimeoutSeconds": "idleTimeoutSeconds",
        "upscalingMode": "upscalingMode",
        "env": "env",
        "envFrom": "envFrom",
        "volumeMounts": "volumeMounts",
    }

    def __init__(
        self,
        resources=None,
        image=None,
        imagePullPolicy=None,
        securityContext=None,
        idleTimeoutSeconds=None,
        upscalingMode=None,
        env=None,
        envFrom=None,
        volumeMounts=None,
    ):
        self._resources = None
        self._image = None
        self._imagePullPolicy = None
        self._securityContext = None
        self._idleTimeoutSeconds = None
        self._upscalingMode = None
        self._env = None
        self._envFrom = None
        self._volumeMounts = None

        if resources is not None:
            self._resources = resources
        if image is not None:
            self._image = image
        if imagePullPolicy is not None:
            self._imagePullPolicy = imagePullPolicy
        if securityContext is not None:
            self._securityContext = securityContext
        if idleTimeoutSeconds is not None:
            self._idleTimeoutSeconds = idleTimeoutSeconds
        if upscalingMode is not None:
            self._upscalingMode = upscalingMode
        if env is not None:
            self._env = env
        if envFrom is not None:
            self._envFrom = envFrom
        if volumeMounts is not None:
            self._volumeMounts = volumeMounts

    @property
    def resources(self):
        return self._resources

    @resources.setter
    def resources(self, resources):
        self._resources = resources

    @property
    def image(self):
        return self._image

    @image.setter
    def image(self, image):
        self._image = image

    @property
    def imagePullPolicy(self):
        return self._imagePullPolicy

    @imagePullPolicy.setter
    def imagePullPolicy(self, imagePullPolicy):
        self._imagePullPolicy = imagePullPolicy

    @property
    def securityContext(self):
        return self._securityContext

    @securityContext.setter
    def securityContext(self, securityContext):
        self._securityContext = securityContext

    @property
    def idleTimeoutSeconds(self):
        return self._idleTimeoutSeconds

    @idleTimeoutSeconds.setter
    def idleTimeoutSeconds(self, idleTimeoutSeconds):
        self._idleTimeoutSeconds = idleTimeoutSeconds

    @property
    def upscalingMode(self):
        return self._upscalingMode

    @upscalingMode.setter
    def upscalingMode(self, upscalingMode):
        self._upscalingMode = upscalingMode

    @property
    def env(self):
        return self._env

    @env.setter
    def env(self, env):
        self._env = env

    @property
    def envFrom(self):
        return self._envFrom

    @envFrom.setter
    def envFrom(self, envFrom):
        self._envFrom = envFrom

    @property
    def volumeMounts(self):
        return self._volumeMounts

    @volumeMounts.setter
    def volumeMounts(self, volumeMounts):
        self._volumeMounts = volumeMounts

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
        if not isinstance(other, V1AutoScalerOptions):
            return False

        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        """Returns true if both objects are not equal"""
        if not isinstance(other, V1AutoScalerOptions):
            return True

        return self.to_dict() != other.to_dict()
