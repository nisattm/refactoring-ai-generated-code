package edu.abu.coursetracker.config;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.type.LogicalType;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JacksonConfig {

    /**
     * Rejects values of the wrong JSON type instead of silently coercing them
     * (e.g. {@code "3"} for an integer, {@code 3.7} for an integer, {@code 42} for a string).
     */
    @Bean
    Jackson2ObjectMapperBuilderCustomizer strictScalarTypes() {
        return builder -> builder
                .featuresToDisable(MapperFeature.ALLOW_COERCION_OF_SCALARS)
                .featuresToDisable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
                .postConfigurer(mapper -> {
                    var textual = mapper.coercionConfigFor(LogicalType.Textual);
                    textual.setCoercion(CoercionInputShape.Integer, CoercionAction.Fail);
                    textual.setCoercion(CoercionInputShape.Float, CoercionAction.Fail);
                    textual.setCoercion(CoercionInputShape.Boolean, CoercionAction.Fail);
                });
    }
}
