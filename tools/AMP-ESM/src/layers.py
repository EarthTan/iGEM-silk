#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Sep 27 13:11:00 2019

Script for Multi-Head Scaled Dot-Product Attention and Context Attention layers
Adapted for TensorFlow 2.16 / Keras 3.

@author: Chenkai Li (original)
"""

import tensorflow as tf
from tensorflow.keras import backend as K
from tensorflow.keras import initializers, regularizers, constraints, activations
from tensorflow.keras.layers import Layer


class Attention(Layer):
    """
    Adapted from https://github.com/lzfelix/keras_attention

    Implementation based on the work of Yang et al. "Hierarchical
    Attention Networks for Document Classification".
    [https://www.aclweb.org/anthology/N16-1174]

    The mathematical formulation of the model is as follows:
    ```
    u = f(W * h + b),
    a_i = softmax(u_i^T * u_s),
    v_i = \sigma_i a_i * h_i.
    ```
    """

    def __init__(self,
                 activation='tanh',
                 initializer='glorot_normal',
                 return_attention=False,
                 W_regularizer=None, u_regularizer=None, b_regularizer=None,
                 W_constraint=None, u_constraint=None, b_constraint=None,
                 bias=True,
                 **kwargs):
        self.activation = activations.get(activation)
        self.initializer = initializers.get(initializer)
        self.return_attention = return_attention
        self.W_regularizer = regularizers.get(W_regularizer)
        self.u_regularizer = regularizers.get(u_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)
        self.W_constraint = constraints.get(W_constraint)
        self.u_constraint = constraints.get(u_constraint)
        self.b_constraint = constraints.get(b_constraint)
        self.bias = bias
        self.supports_masking = True
        super().__init__(**kwargs)

    def get_config(self):
        config = {
            'activation': activations.serialize(self.activation),
            'initializer': initializers.serialize(self.initializer),
            'return_attention': self.return_attention,
            'W_regularizer': regularizers.serialize(self.W_regularizer),
            'u_regularizer': regularizers.serialize(self.u_regularizer),
            'b_regularizer': regularizers.serialize(self.b_regularizer),
            'W_constraint': constraints.serialize(self.W_constraint),
            'u_constraint': constraints.serialize(self.u_constraint),
            'b_constraint': constraints.serialize(self.b_constraint),
            'bias': self.bias,
        }
        base_config = super().get_config()
        return {**base_config, **config}

    def build(self, input_shape):
        # input_shape: (batch, time, amount_features)
        amount_features = input_shape[-1]
        attention_size = input_shape[-1]

        self.W = self.add_weight(shape=(amount_features, attention_size),
                                 initializer=self.initializer,
                                 regularizer=self.W_regularizer,
                                 constraint=self.W_constraint,
                                 name='attention_W')
        self.b = None
        if self.bias:
            self.b = self.add_weight(shape=(attention_size,),
                                     initializer='zeros',
                                     regularizer=self.b_regularizer,
                                     constraint=self.b_constraint,
                                     name='attention_b')

        self.context = self.add_weight(shape=(attention_size,),
                                       initializer=self.initializer,
                                       regularizer=self.u_regularizer,
                                       constraint=self.u_constraint,
                                       name='attention_us')

        super().build(input_shape)

    def call(self, x, mask=None):
        # U = tanh(H*W + b) (eq. 8)
        ui = K.dot(x, self.W)              # (b, t, a)
        if self.b is not None:
            ui = ui + self.b
        ui = self.activation(ui)           # (b, t, a)

        # Z = U * us (eq. 9)
        us = K.expand_dims(self.context)   # (a, 1)
        ui_us = K.dot(ui, us)              # (b, t, a) * (a, 1) = (b, t, 1)
        ui_us = K.squeeze(ui_us, axis=-1)  # (b, t)

        # alpha = softmax(Z) (eq. 9)
        alpha = self._masked_softmax(ui_us, mask)  # (b, t)
        alpha = K.expand_dims(alpha, axis=-1)      # (b, t, 1)

        if self.return_attention:
            return alpha
        else:
            # v = alpha_i * x_i (eq. 10)
            return K.sum(x * alpha, axis=1)

    def _masked_softmax(self, logits, mask):
        b = K.max(logits, axis=-1, keepdims=True)
        logits = logits - b
        exped = K.exp(logits)
        if mask is not None:
            mask = K.cast(mask, K.floatx())
            exped = exped * mask
        partition = K.sum(exped, axis=-1, keepdims=True)
        partition = K.maximum(partition, K.epsilon())
        return exped / partition

    def compute_output_shape(self, input_shape):
        if self.return_attention:
            return input_shape[:-1]
        else:
            return input_shape[:-2] + input_shape[-1:]

    def compute_mask(self, x, input_mask=None):
        return None


class ScaledDotProductAttention(Layer):
    """Scaled dot-product attention used inside MultiHeadAttention."""

    def __init__(self, return_attention=False, history_only=False, **kwargs):
        self.return_attention = return_attention
        self.history_only = history_only
        self.supports_masking = True
        super().__init__(**kwargs)

    def get_config(self):
        config = {'return_attention': self.return_attention,
                  'history_only': self.history_only}
        base_config = super().get_config()
        return {**base_config, **config}

    def compute_output_shape(self, input_shape):
        q, k, v = input_shape
        output_shape = q[:-1] + (v[-1],)
        if self.return_attention:
            return [output_shape, q[:-1] + (k[-2],)]
        return output_shape

    def compute_mask(self, inputs, input_mask=None):
        if isinstance(input_mask, list):
            return input_mask[0]
        return input_mask

    def call(self, inputs, mask=None):
        if isinstance(inputs, list):
            q, k, v = inputs
        else:
            q = k = v = inputs
        if isinstance(mask, list):
            q_mask, k_mask, v_mask = mask
        else:
            q_mask = k_mask = v_mask = mask

        # feature dim of keys/queries for scaling
        ki = K.cast(K.shape(k)[-1], K.floatx())
        # scaled logits
        logits = K.batch_dot(q, k, axes=2)
        logits = logits / K.sqrt(ki)

        if self.history_only:
            # causal mask: forbid attending to the future
            seq_len = K.shape(logits)[-1]
            idx = K.arange(0, seq_len)
            causal = K.cast(idx[None, :] <= idx[:, None], K.floatx())
            logits = logits * causal + (1.0 - causal) * (-1e9)

        if q_mask is not None:
            q_mask_f = K.cast(q_mask, K.floatx())            # (B, Tq)
            k_mask_f = K.cast(k_mask, K.floatx())            # (B, Tk)
            # broadcast to (B, Tq, Tk)
            attn_mask = k_mask_f[:, None, :] * q_mask_f[:, :, None]
            logits = logits - (1.0 - attn_mask) * 1e9

        weights = K.softmax(logits, axis=-1)
        # apply v_mask on values
        if v_mask is not None:
            v_mask_f = K.cast(v_mask, K.floatx())            # (B, Tv)
            weights = weights * v_mask_f[:, :, None]
            weights = weights / K.maximum(K.sum(weights, axis=-1, keepdims=True), K.epsilon())

        output = K.batch_dot(weights, v, axes=[2, 1])       # (B, Tq, Dv)

        if self.return_attention:
            return [output, weights]
        return output


class MultiHeadAttention(Layer):
    """
    Adapted from https://github.com/CyberZHG/keras-multi-head

    Multi-head scaled dot-product attention.
    Original naming of weights is preserved (Wq/Wk/Wv/Wo + bq/bk/bv/bo)
    so that pretrained checkpoints from Keras 2 / TF 1 load correctly.
    """

    def __init__(self,
                 head_num,
                 activation='relu',
                 use_bias=True,
                 kernel_initializer='glorot_normal',
                 bias_initializer='zeros',
                 kernel_regularizer=None,
                 bias_regularizer=None,
                 kernel_constraint=None,
                 bias_constraint=None,
                 history_only=False,
                 return_multi_attention=False,
                 **kwargs):
        self.head_num = head_num
        self.activation = activations.get(activation)
        self.use_bias = use_bias
        self.kernel_initializer = initializers.get(kernel_initializer)
        self.bias_initializer = initializers.get(bias_initializer)
        self.kernel_regularizer = regularizers.get(kernel_regularizer)
        self.bias_regularizer = regularizers.get(bias_regularizer)
        self.kernel_constraint = constraints.get(kernel_constraint)
        self.bias_constraint = constraints.get(bias_constraint)
        self.history_only = history_only
        self.return_multi_attention = return_multi_attention
        self.supports_masking = True

        self.Wq = self.Wk = self.Wv = self.Wo = None
        self.bq = self.bk = self.bv = self.bo = None
        super().__init__(**kwargs)

    def get_config(self):
        config = {
            'head_num': self.head_num,
            'activation': activations.serialize(self.activation),
            'use_bias': self.use_bias,
            'kernel_initializer': initializers.serialize(self.kernel_initializer),
            'bias_initializer': initializers.serialize(self.bias_initializer),
            'kernel_regularizer': regularizers.serialize(self.kernel_regularizer),
            'bias_regularizer': regularizers.serialize(self.bias_regularizer),
            'kernel_constraint': constraints.serialize(self.kernel_constraint),
            'bias_constraint': constraints.serialize(self.bias_constraint),
            'history_only': self.history_only,
            'return_multi_attention': self.return_multi_attention,
        }
        base_config = super().get_config()
        return {**base_config, **config}

    def compute_output_shape(self, input_shape):
        if isinstance(input_shape, list):
            q, k, v = input_shape
        else:
            q = k = v = input_shape
        if self.return_multi_attention:
            return (q[0], self.head_num, q[1], k[1])
        return q[:-1] + (v[-1],)

    def compute_mask(self, inputs, input_mask=None):
        if isinstance(input_mask, list):
            return input_mask[0]
        return input_mask

    def build(self, input_shape):
        if isinstance(input_shape, list):
            q, k, v = input_shape
        else:
            q = k = v = input_shape
        feature_dim = int(v[-1])
        if feature_dim % self.head_num != 0:
            raise IndexError('Invalid head number %d with the given input dim %d' % (self.head_num, feature_dim))

        self.Wq = self.add_weight(shape=(int(q[-1]), feature_dim),
                                  initializer=self.kernel_initializer,
                                  regularizer=self.kernel_regularizer,
                                  constraint=self.kernel_constraint,
                                  name='%s_Wq' % self.name)
        if self.use_bias:
            self.bq = self.add_weight(shape=(feature_dim,),
                                      initializer=self.bias_initializer,
                                      regularizer=self.bias_regularizer,
                                      constraint=self.bias_constraint,
                                      name='%s_bq' % self.name)
        self.Wk = self.add_weight(shape=(int(k[-1]), feature_dim),
                                  initializer=self.kernel_initializer,
                                  regularizer=self.kernel_regularizer,
                                  constraint=self.kernel_constraint,
                                  name='%s_Wk' % self.name)
        if self.use_bias:
            self.bk = self.add_weight(shape=(feature_dim,),
                                      initializer=self.bias_initializer,
                                      regularizer=self.bias_regularizer,
                                      constraint=self.bias_constraint,
                                      name='%s_bk' % self.name)
        self.Wv = self.add_weight(shape=(int(v[-1]), feature_dim),
                                  initializer=self.kernel_initializer,
                                  regularizer=self.kernel_regularizer,
                                  constraint=self.kernel_constraint,
                                  name='%s_Wv' % self.name)
        if self.use_bias:
            self.bv = self.add_weight(shape=(feature_dim,),
                                      initializer=self.bias_initializer,
                                      regularizer=self.bias_regularizer,
                                      constraint=self.bias_constraint,
                                      name='%s_bv' % self.name)
        self.Wo = self.add_weight(shape=(feature_dim, feature_dim),
                                  initializer=self.kernel_initializer,
                                  regularizer=self.kernel_regularizer,
                                  constraint=self.kernel_constraint,
                                  name='%s_Wo' % self.name)
        if self.use_bias:
            self.bo = self.add_weight(shape=(feature_dim,),
                                      initializer=self.bias_initializer,
                                      regularizer=self.bias_regularizer,
                                      constraint=self.bias_constraint,
                                      name='%s_bo' % self.name)
        super().build(input_shape)

    @staticmethod
    def _reshape_to_batches(x, head_num):
        input_shape = K.shape(x)
        batch_size, seq_len, feature_dim = input_shape[0], input_shape[1], input_shape[2]
        head_dim = feature_dim // head_num
        x = K.reshape(x, (batch_size, seq_len, head_num, head_dim))
        x = K.permute_dimensions(x, (0, 2, 1, 3))
        return K.reshape(x, (batch_size * head_num, seq_len, head_dim))

    @staticmethod
    def _reshape_from_batches(x, head_num):
        input_shape = K.shape(x)
        batch_size, seq_len, feature_dim = input_shape[0], input_shape[1], input_shape[2]
        x = K.reshape(x, (batch_size // head_num, head_num, seq_len, feature_dim))
        x = K.permute_dimensions(x, (0, 2, 1, 3))
        return K.reshape(x, (batch_size // head_num, seq_len, feature_dim * head_num))

    @staticmethod
    def _reshape_attention_from_batches(x, head_num):
        input_shape = K.shape(x)
        batch_size, seq_len = input_shape[0], input_shape[1]
        return K.reshape(x, (batch_size // head_num, head_num, seq_len, seq_len))

    @staticmethod
    def _reshape_mask(mask, head_num):
        if mask is None:
            return mask
        seq_len = K.shape(mask)[1]
        mask = K.expand_dims(mask, axis=1)
        mask = K.tile(mask, [1, head_num, 1])
        return K.reshape(mask, (-1, seq_len))

    def call(self, inputs, mask=None):
        if isinstance(inputs, list):
            q, k, v = inputs
        else:
            q = k = v = inputs
        if isinstance(mask, list):
            q_mask, k_mask, v_mask = mask
        else:
            q_mask = k_mask = v_mask = mask

        q = K.dot(q, self.Wq)
        k = K.dot(k, self.Wk)
        v = K.dot(v, self.Wv)
        if self.use_bias:
            q = q + self.bq
            k = k + self.bk
            v = v + self.bv
        if self.activation is not None:
            q = self.activation(q)
            k = self.activation(k)
            v = self.activation(v)

        y, a = ScaledDotProductAttention(
            return_attention=True,
            history_only=self.history_only,
            name='%s-Attention' % self.name,
        )(
            inputs=[
                self._reshape_to_batches(q, self.head_num),
                self._reshape_to_batches(k, self.head_num),
                self._reshape_to_batches(v, self.head_num),
            ],
            mask=[
                self._reshape_mask(q_mask, self.head_num),
                self._reshape_mask(k_mask, self.head_num),
                self._reshape_mask(v_mask, self.head_num),
            ],
        )

        y = self._reshape_from_batches(y, self.head_num)
        a = self._reshape_attention_from_batches(a, self.head_num)
        y = K.dot(y, self.Wo)
        if self.use_bias:
            y = y + self.bo
        if self.activation is not None:
            y = self.activation(y)

        if self.return_multi_attention:
            return a
        return y
