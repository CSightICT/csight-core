# CSight E3 binary defect model card

This package identifies the E3 DINOv2 ViT-S/14 binary any-defect checkpoint used
by the synthetic CSight scenario demo. It emits one advisory defect probability;
it does not emit a defect type, location, mask, severity, or policy decision.

The input is one RGB image resized to 1024 x 1024 without preserving aspect
ratio, with ImageNet normalization. The frozen threshold is `0.8984375`. A score
at or above it is a high-confidence defect candidate. A lower score requires
human review and never confirms that an item is normal.

The reported held-out Kaputt metrics describe one restricted public research
dataset and are not reproduced by this runtime. They do not establish performance
on a customer product or permit a commercial pilot. Keep the checkpoint and
Kaputt data outside Git. A human remains responsible for every final decision.
