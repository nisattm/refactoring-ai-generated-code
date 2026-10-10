package edu.abu.coursetracker.web;

import edu.abu.coursetracker.dto.CourseRequest;
import edu.abu.coursetracker.dto.CourseResponse;
import edu.abu.coursetracker.service.CourseService;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/courses")
@Tag(name = "Courses")
public class CourseController {

    private final CourseService service;
    private final RequestBodyReader bodyReader;

    public CourseController(CourseService service, RequestBodyReader bodyReader) {
        this.service = service;
        this.bodyReader = bodyReader;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public CourseResponse create(@Valid @RequestBody CourseRequest request) {
        return service.create(request);
    }

    @GetMapping
    public List<CourseResponse> list() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public CourseResponse get(@PathVariable Long id) {
        return service.get(id);
    }

    @PutMapping("/{id}")
    public CourseResponse update(
            @PathVariable Long id,
            @io.swagger.v3.oas.annotations.parameters.RequestBody(
                    required = true, content = @Content(schema = @Schema(implementation = CourseRequest.class)))
            @RequestBody(required = false) byte[] body) {
        service.get(id); // 404 takes precedence over an invalid body
        return service.update(id, bodyReader.read(body, CourseRequest.class));
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long id) {
        service.delete(id);
    }
}
