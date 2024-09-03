from abc import ABCMeta
from random import Random

from modules.model.StableDiffusionModel import StableDiffusionModel, StableDiffusionModelEmbedding
from modules.modelSetup.BaseModelSetup import BaseModelSetup
from modules.modelSetup.mixin.ModelSetupDebugMixin import ModelSetupDebugMixin
from modules.modelSetup.mixin.ModelSetupDiffusionLossMixin import ModelSetupDiffusionLossMixin
from modules.modelSetup.mixin.ModelSetupDiffusionMixin import ModelSetupDiffusionMixin
from modules.modelSetup.mixin.ModelSetupEmbeddingMixin import ModelSetupEmbeddingMixin
from modules.modelSetup.mixin.ModelSetupNoiseMixin import ModelSetupNoiseMixin
from modules.module.AdditionalEmbeddingWrapper import AdditionalEmbeddingWrapper
from modules.util.checkpointing_util import (
    create_checkpointed_forward,
    enable_checkpointing_for_clip_encoder_layers,
    enable_checkpointing_for_sdxl_transformer_blocks,
)
from modules.util.config.TrainConfig import TrainConfig
from modules.util.conv_util import apply_circular_padding_to_conv2d
from modules.util.dtype_util import create_autocast_context
from modules.util.enum.AttentionMechanism import AttentionMechanism
from modules.util.enum.TrainingMethod import TrainingMethod
from modules.util.TrainProgress import TrainProgress

import torch
from torch import Tensor
from torch.utils.checkpoint import checkpoint

from diffusers.models.attention_processor import AttnProcessor, AttnProcessor2_0, XFormersAttnProcessor
from diffusers.utils import is_xformers_available


class BaseStableDiffusionSetup(
    BaseModelSetup,
    ModelSetupDiffusionLossMixin,
    ModelSetupDebugMixin,
    ModelSetupNoiseMixin,
    ModelSetupDiffusionMixin,
    ModelSetupEmbeddingMixin,
    metaclass=ABCMeta,
):

    def __init__(self, train_device: torch.device, temp_device: torch.device, debug_mode: bool):
        super(BaseStableDiffusionSetup, self).__init__(train_device, temp_device, debug_mode)

    def _setup_optimizations(
            self,
            model: StableDiffusionModel,
            config: TrainConfig,
    ):
        if config.attention_mechanism == AttentionMechanism.DEFAULT:
            model.unet.set_attn_processor(AttnProcessor())
        elif config.attention_mechanism == AttentionMechanism.XFORMERS and is_xformers_available():
            try:
                model.unet.set_attn_processor(XFormersAttnProcessor())
                model.vae.enable_xformers_memory_efficient_attention()
            except Exception as e:
                print(
                    "Could not enable memory efficient attention. Make sure xformers is installed"
                    f" correctly and a GPU is available: {e}"
                )
        elif config.attention_mechanism == AttentionMechanism.SDP:
            model.unet.set_attn_processor(AttnProcessor2_0())

            if is_xformers_available():
                try:
                    model.vae.enable_xformers_memory_efficient_attention()
                except Exception as e:
                    print(
                        "Could not enable memory efficient attention. Make sure xformers is installed"
                        f" correctly and a GPU is available: {e}"
                    )

        if config.gradient_checkpointing.enabled():
            model.vae.enable_gradient_checkpointing()
            model.unet.enable_gradient_checkpointing()
            enable_checkpointing_for_sdxl_transformer_blocks(
                model.unet, self.train_device, self.temp_device, config.gradient_checkpointing.offload())
            enable_checkpointing_for_clip_encoder_layers(
                model.text_encoder, self.train_device, self.temp_device, config.gradient_checkpointing.offload())

        if config.force_circular_padding:
            apply_circular_padding_to_conv2d(model.vae)
            apply_circular_padding_to_conv2d(model.unet)
            if model.unet_lora is not None:
                apply_circular_padding_to_conv2d(model.unet_lora)

        model.autocast_context, model.train_dtype = create_autocast_context(self.train_device, config.train_dtype, [
            config.weight_dtypes().text_encoder,
            config.weight_dtypes().unet,
            config.weight_dtypes().vae,
            config.weight_dtypes().lora if config.training_method == TrainingMethod.LORA else None,
            config.weight_dtypes().embedding if config.train_any_embedding() else None,
        ], config.enable_autocast_cache)

    def _setup_additional_embeddings(
            self,
            model: StableDiffusionModel,
            config: TrainConfig,
    ):
        model.additional_embeddings = []
        for i, embedding_config in enumerate(config.additional_embeddings):
            embedding_state = model.additional_embedding_states[i]
            if embedding_state is None:
                embedding_state = self._create_new_embedding(
                    model.tokenizer,
                    model.text_encoder,
                    config.additional_embeddings[i].initial_embedding_text,
                    config.additional_embeddings[i].token_count,
                )

            embedding_state = embedding_state.to(
                dtype=model.text_encoder.get_input_embeddings().weight.dtype,
                device=self.train_device,
            ).detach()

            embedding = StableDiffusionModelEmbedding(
                embedding_config.uuid, embedding_state, embedding_config.placeholder,
            )
            model.additional_embeddings.append(embedding)
            self._add_embedding_to_tokenizer(model.tokenizer, embedding.text_tokens)

    def _setup_embedding(
            self,
            model: StableDiffusionModel,
            config: TrainConfig,
    ):
        model.embedding = None

        embedding_state = model.embedding_state
        if embedding_state is None:
            embedding_state = self._create_new_embedding(
                model.tokenizer,
                model.text_encoder,
                config.embedding.initial_embedding_text,
                config.embedding.token_count,
            )

        embedding_state = embedding_state.to(
            dtype=model.text_encoder.get_input_embeddings().weight.dtype,
            device=self.train_device,
        ).detach()

        model.embedding = StableDiffusionModelEmbedding(
            config.embedding.uuid, embedding_state, config.embedding.placeholder,
        )
        self._add_embedding_to_tokenizer(model.tokenizer, model.embedding.text_tokens)

    def _setup_embedding_wrapper(
            self,
            model: StableDiffusionModel,
            config: TrainConfig,
    ):
        model.embedding_wrapper = AdditionalEmbeddingWrapper(
            tokenizer=model.tokenizer,
            orig_module=model.text_encoder.text_model.embeddings.token_embedding,
            additional_embeddings=[embedding.text_encoder_vector for embedding in model.additional_embeddings]
                                  + ([] if model.embedding is None else [model.embedding.text_encoder_vector]),
            additional_embedding_placeholders=[embedding.placeholder for embedding in model.additional_embeddings]
                                  + ([] if model.embedding is None else [model.embedding.placeholder]),
            additional_embedding_names=[embedding.uuid for embedding in model.additional_embeddings]
                                  + ([] if model.embedding is None else [model.embedding.uuid]),
        )
        model.embedding_wrapper.hook_to_module()

    def predict(
            self,
            model: StableDiffusionModel,
            batch: dict,
            config: TrainConfig,
            train_progress: TrainProgress,
            *,
            deterministic: bool = False,
    ) -> dict:
        with model.autocast_context:
            generator = torch.Generator(device=config.train_device)
            generator.manual_seed(train_progress.global_step)
            rand = Random(train_progress.global_step)

            is_align_prop_step = config.align_prop and (rand.random() < config.align_prop_probability)

            vae_scaling_factor = model.vae.config['scaling_factor']

            text_encoder_output = model.encode_text(
                tokens=batch['tokens'],
                text_encoder_layer_skip=config.text_encoder_layer_skip,
                text_encoder_output=batch[
                    'text_encoder_hidden_state'] if not config.train_text_encoder_or_embedding() else None,
            )

            latent_image = batch['latent_image']
            scaled_latent_image = latent_image * vae_scaling_factor

            scaled_latent_conditioning_image = None
            if config.model_type.has_conditioning_image_input():
                scaled_latent_conditioning_image = batch['latent_conditioning_image'] * vae_scaling_factor

            latent_noise = self._create_noise(scaled_latent_image, config, generator)

            if is_align_prop_step and not deterministic:
                negative_text_encoder_output = model.encode_text(
                    text="",
                    text_encoder_layer_skip=config.text_encoder_layer_skip,
                ).expand((scaled_latent_image.shape[0], -1, -1))

                model.noise_scheduler.set_timesteps(config.align_prop_steps)

                scaled_noisy_latent_image = latent_noise

                timestep_high = int(config.align_prop_steps * config.max_noising_strength)
                timestep_low = \
                    int(config.align_prop_steps * config.max_noising_strength * (
                            1.0 - config.align_prop_truncate_steps))
                truncate_timestep_index = config.align_prop_steps - rand.randint(timestep_low, timestep_high)

                checkpointed_unet = create_checkpointed_forward(model.unet, self.train_device)

                for step in range(config.align_prop_steps):
                    timestep = model.noise_scheduler.timesteps[step] \
                        .expand((scaled_latent_image.shape[0],)) \
                        .to(device=model.unet.device)

                    if config.model_type.has_mask_input() and config.model_type.has_conditioning_image_input():
                        latent_input = torch.concat(
                            [scaled_noisy_latent_image, batch['latent_mask'], scaled_latent_conditioning_image], 1
                        )
                    else:
                        latent_input = scaled_noisy_latent_image

                    if config.model_type.has_depth_input():
                        predicted_latent_noise = checkpointed_unet(
                            latent_input,
                            timestep,
                            text_encoder_output,
                            batch['latent_depth'],
                        ).sample

                        negative_predicted_latent_noise = checkpointed_unet(
                            latent_input,
                            timestep,
                            negative_text_encoder_output,
                            batch['latent_depth'],
                        ).sample
                    else:
                        predicted_latent_noise = checkpointed_unet(
                            latent_input,
                            timestep,
                            text_encoder_output,
                        ).sample

                        negative_predicted_latent_noise = checkpointed_unet(
                            latent_input,
                            timestep,
                            negative_text_encoder_output,
                        ).sample

                    cfg_grad = (predicted_latent_noise - negative_predicted_latent_noise)
                    cfg_predicted_latent_noise = negative_predicted_latent_noise + config.align_prop_cfg_scale * cfg_grad

                    scaled_noisy_latent_image = model.noise_scheduler \
                        .step(cfg_predicted_latent_noise, timestep[0].long(), scaled_noisy_latent_image) \
                        .prev_sample

                    if step < truncate_timestep_index:
                        scaled_noisy_latent_image = scaled_noisy_latent_image.detach()

                    if self.debug_mode:
                        with torch.no_grad():
                            # predicted image
                            predicted_image = model.vae.decode(
                                scaled_noisy_latent_image.to(dtype=model.vae.dtype) / vae_scaling_factor).sample
                            predicted_image = predicted_image.clamp(-1, 1)
                            self._save_image(
                                predicted_image,
                                config.debug_dir + "/training_batches",
                                "2-predicted_image_" + str(step),
                                train_progress.global_step
                            )

                predicted_latent_image = scaled_noisy_latent_image / vae_scaling_factor
                predicted_latent_image = predicted_latent_image.to(dtype=model.vae.dtype)

                predicted_image = []
                for x in predicted_latent_image.split(1):
                    predicted_image.append(checkpoint(
                        model.vae.decode,
                        x,
                        use_reentrant=False
                    ).sample)
                predicted_image = torch.cat(predicted_image)

                model_output_data = {
                    'loss_type': 'align_prop',
                    'predicted': predicted_image,
                }
            else:
                timestep = self._get_timestep_discrete(
                    model.noise_scheduler.config['num_train_timesteps'],
                    deterministic,
                    generator,
                    scaled_latent_image.shape[0],
                    config,
                )

                scaled_noisy_latent_image = self._add_noise_discrete(
                    scaled_latent_image,
                    latent_noise,
                    timestep,
                    model.noise_scheduler.betas,
                )

                if config.model_type.has_mask_input() and config.model_type.has_conditioning_image_input():
                    latent_input = torch.concat(
                        [scaled_noisy_latent_image, batch['latent_mask'], scaled_latent_conditioning_image], 1
                    )
                else:
                    latent_input = scaled_noisy_latent_image

                if config.model_type.has_depth_input():
                    predicted_latent_noise = model.unet(
                        latent_input, timestep, text_encoder_output, batch['latent_depth']
                    ).sample
                else:
                    predicted_latent_noise = model.unet(
                        latent_input, timestep, text_encoder_output
                    ).sample

                model_output_data = {}

                if model.noise_scheduler.config.prediction_type == 'epsilon':
                    model_output_data = {
                        'loss_type': 'target',
                        'timestep': timestep,
                        'predicted': predicted_latent_noise,
                        'target': latent_noise,
                    }
                elif model.noise_scheduler.config.prediction_type == 'v_prediction':
                    target_velocity = model.noise_scheduler.get_velocity(scaled_latent_image, latent_noise, timestep)
                    model_output_data = {
                        'loss_type': 'target',
                        'timestep': timestep,
                        'predicted': predicted_latent_noise,
                        'target': target_velocity,
                    }

            if self.debug_mode:
                with torch.no_grad():
                    self._save_text(
                        self._decode_tokens(batch['tokens'], model.tokenizer),
                        config.debug_dir + "/training_batches",
                        "7-prompt",
                        train_progress.global_step,
                    )

                    if is_align_prop_step:
                        # noise
                        noise = model.vae.decode(latent_noise / vae_scaling_factor).sample
                        noise = noise.clamp(-1, 1)
                        self._save_image(
                            noise,
                            config.debug_dir + "/training_batches",
                            "1-noise",
                            train_progress.global_step
                        )

                        # image
                        image = model.vae.decode(scaled_latent_image / vae_scaling_factor).sample
                        image = image.clamp(-1, 1)
                        self._save_image(
                            image,
                            config.debug_dir + "/training_batches",
                            "2-image",
                            train_progress.global_step
                        )
                    else:
                        # noise
                        noise = model.vae.decode(latent_noise / vae_scaling_factor).sample
                        noise = noise.clamp(-1, 1)
                        self._save_image(
                            noise,
                            config.debug_dir + "/training_batches",
                            "1-noise",
                            train_progress.global_step
                        )

                        # predicted noise
                        predicted_noise = model.vae.decode(predicted_latent_noise / vae_scaling_factor).sample
                        predicted_noise = predicted_noise.clamp(-1, 1)
                        self._save_image(
                            predicted_noise,
                            config.debug_dir + "/training_batches",
                            "2-predicted_noise",
                            train_progress.global_step
                        )

                        # noisy image
                        noisy_latent_image = scaled_noisy_latent_image / vae_scaling_factor
                        noisy_image = model.vae.decode(noisy_latent_image).sample
                        noisy_image = noisy_image.clamp(-1, 1)
                        self._save_image(
                            noisy_image,
                            config.debug_dir + "/training_batches",
                            "3-noisy_image",
                            train_progress.global_step
                        )

                        # predicted image
                        alphas_cumprod = model.noise_scheduler.alphas_cumprod.to(config.train_device, dtype=model.vae.dtype)
                        sqrt_alpha_prod = alphas_cumprod[timestep] ** 0.5
                        sqrt_alpha_prod = sqrt_alpha_prod.flatten().reshape(-1, 1, 1, 1)

                        sqrt_one_minus_alpha_prod = (1 - alphas_cumprod[timestep]) ** 0.5
                        sqrt_one_minus_alpha_prod = sqrt_one_minus_alpha_prod.flatten().reshape(-1, 1, 1, 1)

                        scaled_predicted_latent_image = \
                            (
                                    scaled_noisy_latent_image - predicted_latent_noise * sqrt_one_minus_alpha_prod) / sqrt_alpha_prod
                        predicted_latent_image = scaled_predicted_latent_image / vae_scaling_factor
                        predicted_image = model.vae.decode(predicted_latent_image).sample
                        predicted_image = predicted_image.clamp(-1, 1)
                        self._save_image(
                            predicted_image,
                            config.debug_dir + "/training_batches",
                            "4-predicted_image",
                            model.train_progress.global_step
                        )

                        # image
                        image = model.vae.decode(latent_image).sample
                        image = image.clamp(-1, 1)
                        self._save_image(
                            image,
                            config.debug_dir + "/training_batches",
                            "5-image",
                            model.train_progress.global_step
                        )

                        # conditioning image
                        if config.model_type.has_conditioning_image_input():
                            conditioning_image = model.vae.decode(
                                scaled_latent_conditioning_image / vae_scaling_factor).sample
                            conditioning_image = conditioning_image.clamp(-1, 1)
                            self._save_image(
                                conditioning_image,
                                config.debug_dir + "/training_batches",
                                "6-conditioning_image",
                                train_progress.global_step
                            )

            model_output_data['prediction_type'] = model.noise_scheduler.config.prediction_type
            return model_output_data

    def calculate_loss(
            self,
            model: StableDiffusionModel,
            batch: dict,
            data: dict,
            config: TrainConfig,
    ) -> Tensor:
        return self._diffusion_losses(
            batch=batch,
            data=data,
            config=config,
            train_device=self.train_device,
            betas=model.noise_scheduler.betas.to(device=self.train_device),
        ).mean()
