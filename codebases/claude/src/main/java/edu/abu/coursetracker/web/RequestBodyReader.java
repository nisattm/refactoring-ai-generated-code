package edu.abu.coursetracker.web;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import edu.abu.coursetracker.exception.InvalidRequestException;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.io.IOException;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

/**
 * Parses and validates a request body by hand. PUT endpoints use this so that the path resource can be
 * looked up first: a missing resource must yield 404 even when the body is also malformed or invalid,
 * which is impossible with {@code @Valid @RequestBody} because Spring binds the body before the handler runs.
 */
@Component
public class RequestBodyReader {

    private final ObjectMapper objectMapper;
    private final Validator validator;

    public RequestBodyReader(ObjectMapper objectMapper, Validator validator) {
        this.objectMapper = objectMapper;
        this.validator = validator;
    }

    public <T> T read(byte[] body, Class<T> type) {
        if (body == null || body.length == 0) {
            throw new InvalidRequestException("Request body is required");
        }
        T value;
        try {
            value = objectMapper.readValue(body, type);
        } catch (JsonProcessingException e) {
            throw new InvalidRequestException(describe(e));
        } catch (IOException e) {
            throw new InvalidRequestException("Request body could not be read");
        }
        if (value == null) {
            throw new InvalidRequestException("Request body is required");
        }
        Set<ConstraintViolation<T>> violations = validator.validate(value);
        if (!violations.isEmpty()) {
            throw new InvalidRequestException(violations.stream()
                    .map(v -> v.getPropertyPath() + " " + v.getMessage())
                    .sorted()
                    .collect(Collectors.joining("; ")));
        }
        return value;
    }

    /** Builds a message for a Jackson failure; shared with the handler for {@code @RequestBody} parse errors. */
    static String describe(JsonProcessingException e) {
        if (e instanceof JsonMappingException mapping && !mapping.getPath().isEmpty()) {
            String field = mapping.getPath().stream()
                    .map(ref -> ref.getFieldName() != null ? ref.getFieldName() : "[" + ref.getIndex() + "]")
                    .collect(Collectors.joining("."));
            return "Invalid value for field '" + field + "'";
        }
        return "Malformed JSON request body";
    }
}
