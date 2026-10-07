# check=skip=InvalidDefaultArgInFrom
#
# The skipped check wants the ARG below to default to a usable image. Defaulting
# it to a real one would put the pinned tag in a second place, which is what
# versions.env exists to prevent, so the default is deliberately unusable.

# The pinned tool image, plus this project's Python pins.
#
# The image ships its own Python stack and no linter at all, so the versions
# requirements.txt names are not what a bare container runs. Putting them in a
# layer is what makes them survive a restart, which installing into a running
# container does not.
#
# Contract: BASE is the image versions.env pins, passed by the build. The file
# this writes is how anything running inside can tell which base it is on --
# a container cannot otherwise see its own image.

# The default is not a real image: it exists so a build run without the argument
# fails naming what is missing, rather than quietly resolving to a floating tag.
ARG BASE=set-BASE-to-the-image-pinned-in-versions-env
FROM ${BASE}

# Installed into the interpreter the base ships, so they are there whatever uid
# the container is started with. A user-site install is invisible to every
# other uid, and CI starts it as a different one.
USER root

# PEP 668 marks that interpreter externally managed. Overriding it is the point
# of this layer: replacing the stack the image ships is what it exists to do.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

ARG BASE
RUN printf '%s\n' "${BASE}" > /etc/sar-asic-base-image

# Back to the base's own user. `make image` fails if this stops matching it.
USER 1000:1000
