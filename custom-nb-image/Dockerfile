# Copyright 2022 IBM, Red Hat
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM  quay.io/opendatahub/notebooks:jupyter-minimal-ubi9-python-3.9-2023a_20230302

COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt

RUN pip uninstall pickle5 -y

# Install codeflare-sdk and other libraries
ARG SDK_VERSION=0.*
RUN pip install codeflare-sdk==${SDK_VERSION} \
				datasets==2.6.1 \
				transformers==4.23.1 \
				evaluate==0.3.0

RUN chmod -R g+w /opt/app-root/lib/python3.9/site-packages && \
	fix-permissions /opt/app-root -P
